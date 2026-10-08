"""Contract Compliance Checker — deterministic stage (reconciliation-flow.md §5.2).

Validates every `SAPTransaction` emitted by the SAP Ingestor against the
structured `ContractRules` parsed from contract-001.md (hand-encoded for the
hackathon prototype — see §10 open question). Pure arithmetic, table lookups,
and keyword matches. No LLM.

Pipeline (per §5.2):
  1. Load `ContractRules` from config/agents/contract_compliance.yaml.
  2. Run per-TX checks (RATE_MISMATCH, TRAVEL_RATE_MISMATCH, TRAVEL_CAP_EXCEEDED,
     SUBCONTRACTOR_MARKUP_MISSING, LODGING_LIMIT_EXCEEDED, MEAL_LIMIT_EXCEEDED,
     PER_DIEM_STACKED, ALCOHOL_LINE, PERSONAL_ITEM, ENTERTAINMENT_NEEDS_APPROVAL,
     RECEIPT_REQUIRED_MISSING, MILEAGE_RATE_MISMATCH, CLASSIFICATION_CODE_MISMATCH).
  3. Run cycle-scope checks (CLASSIFICATION_CODE_MISMATCH cycle verdict,
     PRIN_CAP_BREACH).
  4. Build a `ContractComplianceReport` and persist at
     `local/contract_compliance/<cycle>.json`.
  5. Append `CONTRACT_CHECKED` evidence events per-TX plus one cycle-level event.

Idempotency (blueprint §12): the cache key is a SHA-256 of
`(sap_ingest.cycle_header.source_hash || rules.rules_version)`. If upstream SAP
data or the YAML-encoded rules change, the artefact is recomputed; otherwise a
re-run is a no-op.

Node contract (blueprint §5):
  * `do_check(sap_ingest, rules, *, force) -> (report, fresh)` — the lower-level
    helper, usable from the CLI without going through the graph.
  * `node(state) -> state` — the LangGraph wrapper.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from ..config import (
    ContractComplianceConfig,
    PipelineConfig,
    load_agent_config,
    load_pipeline_config,
)
from ..contracts import (
    ComplianceHeuristics,
    ContractComplianceBlock,
    ContractComplianceReport,
    ContractComplianceSummary,
    ContractRules,
    ContractViolation,
    SAPTransaction,
    SapIngestResult,
    Severity,
)
from ..evidence import EvidenceEvent, EvidenceWriter
from ..log import get_logger


_log = get_logger("contract_compliance")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def do_check(
    sap_ingest: SapIngestResult | None = None,
    rules: ContractRules | None = None,
    *,
    force: bool = False,
    pipeline_cfg: PipelineConfig | None = None,
    agent_cfg: ContractComplianceConfig | None = None,
) -> tuple[ContractComplianceReport, bool]:
    """Run the Contract Compliance Checker and return (report, fresh).

    `fresh=False` means the cached artefact was reused (blueprint §12).
    """
    pipeline_cfg = pipeline_cfg or load_pipeline_config()
    agent_cfg = agent_cfg or load_agent_config(
        "contract_compliance", ContractComplianceConfig
    )
    rules = rules or agent_cfg.rules

    sap_ingest = sap_ingest or _load_sap_ingest(pipeline_cfg)

    cycle = sap_ingest.cycle_header.cycle
    out_path = pipeline_cfg.contract_compliance_dir / f"{cycle}.json"
    evidence = EvidenceWriter(pipeline_cfg.evidence_dir)

    cache_key = _cache_key(sap_ingest, rules)

    # ---- 1. Cached hit? (idempotency per blueprint §12) ------------------
    if out_path.exists() and not force:
        try:
            cached = ContractComplianceReport.model_validate_json(
                out_path.read_text("utf-8")
            )
            if cached.contract_rules_version == rules.rules_version:
                _log.info(
                    "contract_check_cached",
                    cycle=cycle,
                    rules_version=rules.rules_version,
                    artefact=str(out_path),
                )
                return cached, False
            _log.info(
                "contract_check_cache_invalid_rules_bumped",
                cycle=cycle,
                cached=cached.contract_rules_version,
                current=rules.rules_version,
            )
        except (ValidationError, ValueError) as exc:
            _log.warning(
                "contract_check_cache_invalid_recomputing",
                cycle=cycle,
                artefact=str(out_path),
                error=str(exc),
            )

    # ---- 2–4. Do the work ------------------------------------------------
    checked_at = datetime.now(timezone.utc)

    per_tx = _run_per_tx_checks(
        sap_ingest.transactions, rules, checked_at=checked_at
    )
    cycle_level = _run_cycle_checks(
        sap_ingest.transactions, rules, cycle_header_classification=None
    )

    summary = _build_summary(per_tx, cycle_level, rules.rules_version)

    report = ContractComplianceReport(
        cycle=cycle,
        contract_rules_version=rules.rules_version,
        per_tx=per_tx,
        cycle_level_violations=cycle_level,
        summary=summary,
        checked_at=checked_at,
    )

    # ---- 5. Persist artefact + evidence stream --------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _write_evidence(report, evidence)

    _log.info(
        "contract_check_done",
        cycle=cycle,
        rules_version=rules.rules_version,
        cache_key=cache_key[:16],
        tx_checked=summary.total_txs_checked,
        pass_count=summary.pass_count,
        violations_hard=summary.violations.get("hard", 0),
        violations_soft=summary.violations.get("soft", 0),
        violations_info=summary.violations.get("info", 0),
        cycle_level_violations=len(cycle_level),
        codes_present=summary.violation_codes_present,
        artefact=str(out_path),
    )
    return report, True


def node(state: Any) -> Any:
    """LangGraph node wrapper. Reads `state.sap_ingest`; writes `state.contract_compliance`."""
    sap_ingest = getattr(state, "sap_ingest", None)
    if sap_ingest is None:
        # Upstream failure — don't fabricate an empty report.
        state.errors.append("contract_compliance: no sap_ingest on state")
        return state

    force = bool(getattr(state, "force", False))
    report, fresh = do_check(sap_ingest=sap_ingest, force=force)
    state.contract_compliance = report
    state.contract_compliance_fresh = fresh
    return state


# ---------------------------------------------------------------------------
# Cache key + sap-ingest loader
# ---------------------------------------------------------------------------


def _cache_key(sap_ingest: SapIngestResult, rules: ContractRules) -> str:
    """SHA-256 of (source_hash || rules_version). Shields the artefact from
    upstream data drift AND from silent contract-rule edits."""
    h = hashlib.sha256()
    h.update(sap_ingest.cycle_header.source_hash.encode("utf-8"))
    h.update(b"\0")
    h.update(rules.rules_version.encode("utf-8"))
    return h.hexdigest()


def _load_sap_ingest(cfg: PipelineConfig) -> SapIngestResult:
    """Load the cached SAP-ingest artefact from disk. Raises if absent."""
    path = cfg.sap_ingested_dir / f"{cfg.cycle}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No SAP ingest artefact for cycle {cfg.cycle} at {path}. "
            "Run `python -m meridian ingest` first."
        )
    return SapIngestResult.model_validate_json(path.read_text("utf-8"))


# ---------------------------------------------------------------------------
# Per-TX check dispatch
# ---------------------------------------------------------------------------


def _run_per_tx_checks(
    txs: list[SAPTransaction],
    rules: ContractRules,
    *,
    checked_at: datetime,
) -> list[ContractComplianceBlock]:
    """Apply every per-TX check and return one block per transaction.

    Group-aware checks (per-day meal cap, per-diem stacking,
    subcontractor-markup sibling lookup, cycle-level classification) are
    pre-computed once over the full stream so individual per-TX passes stay
    O(1).
    """
    # Pre-compute group indices used by multiple checks.
    meal_totals_by_day = _meal_totals_by_employee_day(txs, rules)
    per_diem_days = _per_diem_employee_days(txs, rules)
    meal_tx_by_day = _meal_tx_by_employee_day(txs, rules)
    markup_index = _markup_sibling_index(txs, rules)

    blocks: list[ContractComplianceBlock] = []
    for tx in txs:
        violations: list[ContractViolation] = []

        violations.extend(_check_rate_mismatch(tx, rules))
        violations.extend(_check_travel_rate_mismatch(tx, rules))
        violations.extend(_check_travel_cap_exceeded(tx, rules))
        violations.extend(
            _check_subcontractor_markup_missing(tx, rules, markup_index=markup_index)
        )
        violations.extend(_check_lodging_limit_exceeded(tx, rules))
        violations.extend(
            _check_meal_limit_exceeded(tx, rules, meal_totals=meal_totals_by_day)
        )
        violations.extend(
            _check_per_diem_stacked(
                tx,
                rules,
                per_diem_days=per_diem_days,
                meal_tx_by_day=meal_tx_by_day,
            )
        )
        violations.extend(_check_alcohol_line(tx, rules))
        violations.extend(_check_personal_item(tx, rules))
        violations.extend(_check_entertainment_needs_approval(tx, rules))
        violations.extend(_check_receipt_required_missing(tx, rules))
        violations.extend(_check_mileage_rate_mismatch(tx, rules))
        violations.extend(_check_tx_classification_code(tx, rules))

        blocks.append(
            ContractComplianceBlock(
                tx_id=tx.tx_id,
                status="VIOLATION" if violations else "PASS",
                violations=violations,
                checked_at=checked_at,
                contract_rules_version=rules.rules_version,
            )
        )
    return blocks


# ---------------------------------------------------------------------------
# Cycle-scope checks
# ---------------------------------------------------------------------------


def _run_cycle_checks(
    txs: list[SAPTransaction],
    rules: ContractRules,
    *,
    cycle_header_classification: str | None,
) -> list[ContractViolation]:
    """Checks that take the whole cycle as input (not a single TX)."""
    out: list[ContractViolation] = []

    # CLASSIFICATION_CODE_MISMATCH — cycle verdict based on the modal value.
    classifications = [t.classification for t in txs if t.classification]
    if classifications:
        modal = Counter(classifications).most_common(1)[0][0]
        if modal != rules.classification_code:
            out.append(
                ContractViolation(
                    code="CLASSIFICATION_CODE_MISMATCH",
                    severity="soft",
                    rule_citation="contract-001.md §5 — invoice classification code",
                    detail=(
                        f"Modal cycle classification is {modal!r} but the "
                        f"contract requires {rules.classification_code!r}."
                    ),
                    expected=None,
                    actual=None,
                    scope="cycle",
                )
            )

    # PRIN_CAP_BREACH — PRIN hours / total labour hours > SAP note threshold.
    prin_cap_note = next(
        (n for n in rules.sap_notes if n.rule == "PRIN_CAP_PCT"), None
    )
    if prin_cap_note is not None:
        total_labour_hours = sum(
            (t.quantity or 0.0) for t in txs if t.type == "LABOR"
        )
        prin_hours = sum(
            (t.quantity or 0.0)
            for t in txs
            if t.type == "LABOR" and (t.role_code or "").upper() == "PRIN"
        )
        if total_labour_hours > 0:
            prin_pct = (prin_hours / total_labour_hours) * 100.0
            if prin_pct > prin_cap_note.value:
                out.append(
                    ContractViolation(
                        code="PRIN_CAP_BREACH",
                        severity="soft",
                        rule_citation=(
                            f"contract-001.md §9 SAP note "
                            f"{prin_cap_note.source_date} — PRIN cap "
                            f"{prin_cap_note.value}% of {prin_cap_note.scope}"
                        ),
                        detail=(
                            f"PRIN hours {prin_hours:.2f} / total labour "
                            f"{total_labour_hours:.2f} = {prin_pct:.2f}%, "
                            f"over the {prin_cap_note.value}% monthly cap."
                        ),
                        expected=prin_cap_note.value,
                        actual=round(prin_pct, 4),
                        scope="cycle",
                    )
                )

    return out


# ---------------------------------------------------------------------------
# Pre-computed group indices
# ---------------------------------------------------------------------------


def _meal_totals_by_employee_day(
    txs: list[SAPTransaction], rules: ContractRules
) -> dict[tuple[str, date], float]:
    """Sum meal-receipt amounts per (employee_id, date)."""
    totals: dict[tuple[str, date], float] = defaultdict(float)
    for t in txs:
        if _is_meal_receipt(t, rules):
            if t.employee_id:
                totals[(t.employee_id, t.date)] += t.amount or 0.0
    return dict(totals)


def _meal_tx_by_employee_day(
    txs: list[SAPTransaction], rules: ContractRules
) -> dict[tuple[str, date], list[str]]:
    """List of meal-receipt tx_ids per (employee_id, date)."""
    out: dict[tuple[str, date], list[str]] = defaultdict(list)
    for t in txs:
        if _is_meal_receipt(t, rules) and t.employee_id:
            out[(t.employee_id, t.date)].append(t.tx_id)
    return dict(out)


def _per_diem_employee_days(
    txs: list[SAPTransaction], rules: ContractRules
) -> set[tuple[str, date]]:
    """Set of (employee_id, date) pairs that carry at least one per-diem TX."""
    pairs: set[tuple[str, date]] = set()
    for t in txs:
        if _is_per_diem(t, rules) and t.employee_id:
            pairs.add((t.employee_id, t.date))
    return pairs


def _markup_sibling_index(
    txs: list[SAPTransaction], rules: ContractRules
) -> dict[tuple[str, str | None, date], list[SAPTransaction]]:
    """Group every TX by (project_id, task_code, date) so the markup check can
    look for a sibling markup line without an O(n²) scan."""
    out: dict[tuple[str, str | None, date], list[SAPTransaction]] = defaultdict(list)
    for t in txs:
        out[(t.project_id, t.task_code, t.date)].append(t)
    return dict(out)


# ---------------------------------------------------------------------------
# Individual checks (one per §5.2 code)
# ---------------------------------------------------------------------------


def _check_rate_mismatch(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """RATE_MISMATCH — labour-rate differs from the §3 role-rate table.
    Skipped for travel-time lines (handled by TRAVEL_RATE_MISMATCH)."""
    if tx.type != "LABOR":
        return []
    if _is_travel_time(tx, rules.heuristics):
        return []
    if not tx.role_code or tx.role_code not in rules.role_rates:
        return []
    if tx.rate is None:
        return []
    expected = rules.role_rates[tx.role_code]
    if abs(tx.rate - expected) <= rules.heuristics.rate_match_tolerance_usd:
        return []
    return [
        ContractViolation(
            code="RATE_MISMATCH",
            severity="soft",
            rule_citation="contract-001.md §3 — standard role rate table",
            detail=(
                f"Role {tx.role_code} billed at USD {tx.rate:.2f}/hr, "
                f"contract rate is USD {expected:.2f}/hr."
            ),
            expected=expected,
            actual=tx.rate,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_travel_rate_mismatch(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """TRAVEL_RATE_MISMATCH — travel-time line not at `travel_rate_factor` of the role rate."""
    if tx.type != "LABOR":
        return []
    if not _is_travel_time(tx, rules.heuristics):
        return []
    if not tx.role_code or tx.role_code not in rules.role_rates:
        return []
    if tx.rate is None:
        return []
    expected = rules.role_rates[tx.role_code] * rules.travel_rate_factor
    if abs(tx.rate - expected) <= rules.heuristics.rate_match_tolerance_usd:
        return []
    return [
        ContractViolation(
            code="TRAVEL_RATE_MISMATCH",
            severity="soft",
            rule_citation=(
                "contract-001.md §3 — travel time billable at "
                f"{int(rules.travel_rate_factor * 100)}% of role rate"
            ),
            detail=(
                f"Travel-time role {tx.role_code} billed at USD {tx.rate:.2f}/hr, "
                f"expected USD {expected:.2f}/hr "
                f"({int(rules.travel_rate_factor * 100)}% of "
                f"{rules.role_rates[tx.role_code]:.2f})."
            ),
            expected=round(expected, 4),
            actual=tx.rate,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_travel_cap_exceeded(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """TRAVEL_CAP_EXCEEDED — single travel-time TX quantity > cap.

    Per-TX heuristic per heuristics.trip_grouping == "per_tx" (§10 open:
    proper employee+date-proximity grouping is deferred).
    """
    if tx.type != "LABOR" or not _is_travel_time(tx, rules.heuristics):
        return []
    if tx.quantity is None:
        return []
    cap = rules.travel_cap_hours_per_direction
    if tx.quantity <= cap:
        return []
    return [
        ContractViolation(
            code="TRAVEL_CAP_EXCEEDED",
            severity="soft",
            rule_citation=(
                "contract-001.md §3 — travel time capped at "
                f"{cap:g} hours per traveller per direction"
            ),
            detail=(
                f"Travel-time TX billed {tx.quantity:.2f} h, cap is {cap:g} h "
                "per direction (per-TX heuristic; trip-level grouping TBD)."
            ),
            expected=cap,
            actual=tx.quantity,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_subcontractor_markup_missing(
    tx: SAPTransaction,
    rules: ContractRules,
    *,
    markup_index: dict[tuple[str, str | None, date], list[SAPTransaction]],
) -> Iterable[ContractViolation]:
    """SUBCONTRACTOR_MARKUP_MISSING — subcontractor pass-through TX without a
    sibling markup line.

    Hackathon simplification (documented in the plan): flag the base cost TX
    unless a sibling TX exists on the same (project_id, task_code, date) whose
    amount is within tolerance of `cost * markup_pct/100` and whose description
    mentions "markup".
    """
    if tx.type != "EXPENSE":
        return []
    if not _is_subcontractor_tx(tx, rules.heuristics):
        return []
    if tx.amount is None:
        return []
    expected_markup = tx.amount * (rules.subcontractor_markup_pct / 100.0)
    tol = rules.heuristics.markup_match_tolerance_usd

    siblings = markup_index.get((tx.project_id, tx.task_code, tx.date), [])
    for s in siblings:
        if s.tx_id == tx.tx_id or s.amount is None:
            continue
        desc = (s.description or "").lower()
        if "markup" in desc and abs(s.amount - expected_markup) <= tol:
            return []  # Markup line present — compliant.

    expected_grossed_up = round(tx.amount + expected_markup, 2)
    return [
        ContractViolation(
            code="SUBCONTRACTOR_MARKUP_MISSING",
            severity="soft",
            rule_citation=(
                "contract-001.md §3 — subcontractor pass-through at cost plus "
                f"{rules.subcontractor_markup_pct:g}%"
            ),
            detail=(
                f"TX amount USD {tx.amount:.2f} is cost only. Markup of "
                f"USD {expected_markup:.2f} ({rules.subcontractor_markup_pct:g}%) "
                "not present as a separate line."
            ),
            expected=expected_grossed_up,
            actual=round(tx.amount, 2),
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_lodging_limit_exceeded(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """LODGING_LIMIT_EXCEEDED — hotel amount above metro/other cap."""
    if tx.type != "EXPENSE":
        return []
    if not _is_lodging(tx, rules.heuristics):
        return []
    if tx.amount is None:
        return []
    tier = rules.heuristics.lodging_default_tier
    cap = (
        rules.expense_rules.lodging_cap_metro_usd
        if tier == "metro"
        else rules.expense_rules.lodging_cap_other_usd
    )
    # Lodging is quoted per night in the contract; use per-unit amount when
    # quantity is known so a 2-night block is checked per night.
    per_night = tx.amount / tx.quantity if tx.quantity and tx.quantity > 0 else tx.amount
    if per_night <= cap:
        return []
    return [
        ContractViolation(
            code="LODGING_LIMIT_EXCEEDED",
            severity="soft",
            rule_citation=(
                f"contract-001.md §4 — lodging cap USD {cap:g}/night ({tier})"
            ),
            detail=(
                f"Lodging billed USD {per_night:.2f}/night, cap is USD {cap:g} "
                f"({tier} tier)."
            ),
            expected=cap,
            actual=round(per_night, 2),
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_meal_limit_exceeded(
    tx: SAPTransaction,
    rules: ContractRules,
    *,
    meal_totals: dict[tuple[str, date], float],
) -> Iterable[ContractViolation]:
    """MEAL_LIMIT_EXCEEDED — meals-with-receipt per (employee, day) > cap.

    Fires on the first meal TX of the day for the employee; the detail text
    names the full-day total.
    """
    if tx.type != "EXPENSE" or not _is_meal_receipt(tx, rules):
        return []
    if not tx.employee_id:
        return []
    key = (tx.employee_id, tx.date)
    total = meal_totals.get(key, 0.0)
    cap = rules.expense_rules.meal_cap_usd_per_day
    if total <= cap:
        return []
    return [
        ContractViolation(
            code="MEAL_LIMIT_EXCEEDED",
            severity="soft",
            rule_citation=(
                f"contract-001.md §4 — meals-with-receipt cap USD {cap:g}/day/traveller"
            ),
            detail=(
                f"Meals on {tx.date.isoformat()} for {tx.employee_id} total "
                f"USD {total:.2f}, cap is USD {cap:g}/day."
            ),
            expected=cap,
            actual=round(total, 2),
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_per_diem_stacked(
    tx: SAPTransaction,
    rules: ContractRules,
    *,
    per_diem_days: set[tuple[str, date]],
    meal_tx_by_day: dict[tuple[str, date], list[str]],
) -> Iterable[ContractViolation]:
    """PER_DIEM_STACKED — same traveller/day carries both a per-diem AND a
    meal-with-receipt line while the contract forbids stacking."""
    if rules.expense_rules.per_diem_stackable_with_meal:
        return []
    if tx.type != "EXPENSE" or not tx.employee_id:
        return []
    key = (tx.employee_id, tx.date)
    if key not in per_diem_days:
        return []
    meals_on_day = meal_tx_by_day.get(key, [])
    if not meals_on_day:
        return []
    # Fire on both the per-diem row and each meal row so triage sees the pair
    # from either direction, without double-counting across TXs.
    if _is_per_diem(tx, rules):
        detail = (
            f"Per-diem for {tx.employee_id} on {tx.date.isoformat()} stacked with "
            f"meal receipt(s): {', '.join(meals_on_day)}."
        )
    elif _is_meal_receipt(tx, rules):
        detail = (
            f"Meal receipt for {tx.employee_id} on {tx.date.isoformat()} stacked "
            "with a per-diem claim on the same day."
        )
    else:
        return []
    return [
        ContractViolation(
            code="PER_DIEM_STACKED",
            severity="hard",
            rule_citation=(
                "contract-001.md §4 — per diem not stackable with meal receipts"
            ),
            detail=detail,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_alcohol_line(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """ALCOHOL_LINE — description OR note matches an alcohol keyword.

    §4 says alcohol is "not reimbursable under any circumstance" — the check
    scans the note field too so hotel-folio-style line items (where the alcohol
    marker lands in free text rather than the description, e.g. TX-0029
    "Beverages - team dinner" with note "mixed: incl alcohol") still trigger.
    """
    if tx.type != "EXPENSE":
        return []
    matched = _match_field(tx, rules.heuristics.alcohol_keywords)
    if not matched:
        return []
    field, snippet = matched
    return [
        ContractViolation(
            code="ALCOHOL_LINE",
            severity="hard",
            rule_citation="contract-001.md §4 — alcohol not reimbursable under any circumstance",
            detail=(
                f"TX {field} matches alcohol keyword {snippet!r}; alcohol is not reimbursable."
            ),
            actual=tx.amount,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_personal_item(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """PERSONAL_ITEM — description OR note matches a personal-item keyword."""
    if tx.type != "EXPENSE":
        return []
    matched = _match_field(tx, rules.heuristics.personal_item_keywords)
    if not matched:
        return []
    field, snippet = matched
    return [
        ContractViolation(
            code="PERSONAL_ITEM",
            severity="hard",
            rule_citation="contract-001.md §4 — personal items not reimbursable",
            detail=(f"TX {field} matches personal-item keyword {snippet!r}."),
            actual=tx.amount,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_entertainment_needs_approval(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """ENTERTAINMENT_NEEDS_APPROVAL — description OR note matches an entertainment keyword.
    PL-approval resolution happens in triage (§9); here we always flag."""
    if tx.type != "EXPENSE":
        return []
    matched = _match_field(tx, rules.heuristics.entertainment_keywords)
    if not matched:
        return []
    field, snippet = matched
    return [
        ContractViolation(
            code="ENTERTAINMENT_NEEDS_APPROVAL",
            severity="soft",
            rule_citation=(
                "contract-001.md §4 — entertainment not reimbursable without "
                "prior written Project Lead approval"
            ),
            detail=(
                f"TX {field} matches entertainment keyword {snippet!r}; "
                "PL approval must be confirmed in triage."
            ),
            actual=tx.amount,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_receipt_required_missing(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """RECEIPT_REQUIRED_MISSING — expense > threshold, unit not waived, no backup
    ref OR note explicitly says the receipt is missing."""
    if tx.type != "EXPENSE" or tx.amount is None:
        return []
    if tx.amount <= rules.expense_rules.receipt_threshold_usd:
        return []
    unit = (tx.unit or "").upper()
    if unit in {u.upper() for u in rules.heuristics.receipt_waived_units}:
        return []
    note_blob = (tx.note or "").lower()
    note_says_missing = any(
        m.lower() in note_blob for m in rules.heuristics.receipt_missing_markers
    )
    if tx.backup_ref and not note_says_missing:
        return []
    return [
        ContractViolation(
            code="RECEIPT_REQUIRED_MISSING",
            severity="soft",
            rule_citation=(
                "contract-001.md §4 — receipts required for all expenses above "
                f"USD {rules.expense_rules.receipt_threshold_usd:g} (mileage/per diem waived)"
            ),
            detail=(
                f"Expense USD {tx.amount:.2f} > threshold "
                f"USD {rules.expense_rules.receipt_threshold_usd:g} but no "
                "backup reference is attached (or the note states it is missing)."
            ),
            expected=rules.expense_rules.receipt_threshold_usd,
            actual=tx.amount,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_mileage_rate_mismatch(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """MILEAGE_RATE_MISMATCH — mileage at non-federal rate."""
    if tx.type != "EXPENSE":
        return []
    if (tx.unit or "").upper() != "MI":
        return []
    if tx.rate is None:
        return []
    expected = rules.mileage_rate_usd_per_mile
    if abs(tx.rate - expected) <= rules.heuristics.rate_match_tolerance_usd:
        return []
    return [
        ContractViolation(
            code="MILEAGE_RATE_MISMATCH",
            severity="info",
            rule_citation=(
                "contract-001.md §4 — mileage at the prevailing federal mileage rate"
            ),
            detail=(
                f"Mileage billed at USD {tx.rate:.4f}/mi, configured federal rate "
                f"is USD {expected:.4f}/mi."
            ),
            expected=expected,
            actual=tx.rate,
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


def _check_tx_classification_code(
    tx: SAPTransaction, rules: ContractRules
) -> Iterable[ContractViolation]:
    """Per-TX classification deviation; the cycle-level verdict is emitted
    separately in `_run_cycle_checks`."""
    if not tx.classification:
        return []
    if tx.classification == rules.classification_code:
        return []
    return [
        ContractViolation(
            code="CLASSIFICATION_CODE_MISMATCH",
            severity="soft",
            rule_citation="contract-001.md §5 — invoice classification code",
            detail=(
                f"TX classification {tx.classification!r} differs from the "
                f"contract value {rules.classification_code!r}."
            ),
            scope="tx",
            tx_id=tx.tx_id,
        )
    ]


# ---------------------------------------------------------------------------
# Classification helpers (shared by multiple checks)
# ---------------------------------------------------------------------------


def _norm_desc(tx: SAPTransaction) -> str:
    return (tx.description or "").lower()


def _desc_matches(tx: SAPTransaction, keywords: list[str]) -> bool:
    if not keywords:
        return False
    blob = _norm_desc(tx)
    if not blob:
        return False
    return any(kw.lower() in blob for kw in keywords)


def _match_field(
    tx: SAPTransaction, keywords: list[str]
) -> tuple[str, str] | None:
    """Return (field_name, matched_keyword) if any keyword hits description or
    note. Used by the hard-rule keyword checks (alcohol, personal, entertainment)
    which per §4 are "not reimbursable under any circumstance" and must catch
    the signal wherever it leaks through."""
    if not keywords:
        return None
    desc = (tx.description or "").lower()
    note = (tx.note or "").lower()
    for kw in keywords:
        kw_l = kw.lower()
        if desc and kw_l in desc:
            return ("description", kw)
        if note and kw_l in note:
            return ("note", kw)
    return None


def _is_travel_time(tx: SAPTransaction, h: ComplianceHeuristics) -> bool:
    """LABOR row whose description looks like a travel-time entry."""
    if tx.type != "LABOR":
        return False
    return _desc_matches(tx, h.travel_description_markers)


def _is_lodging(tx: SAPTransaction, h: ComplianceHeuristics) -> bool:
    if (tx.unit or "").upper() == "NIGHT":
        return True
    return _desc_matches(tx, h.lodging_description_markers)


def _is_per_diem(tx: SAPTransaction, rules: ContractRules) -> bool:
    if (tx.unit or "").upper() == "DAY" and _desc_matches(
        tx, rules.heuristics.per_diem_description_markers
    ):
        return True
    return _desc_matches(tx, rules.heuristics.per_diem_description_markers)


def _is_meal_receipt(tx: SAPTransaction, rules: ContractRules) -> bool:
    """Meal receipt — meal keyword in description AND not a per-diem row AND
    not already picked up as an alcohol-only line."""
    if tx.type != "EXPENSE":
        return False
    if _is_per_diem(tx, rules):
        return False
    if not _desc_matches(tx, rules.heuristics.meal_description_markers):
        return False
    return True


def _is_subcontractor_tx(tx: SAPTransaction, h: ComplianceHeuristics) -> bool:
    emp = (tx.employee_id or "").upper()
    if any(emp.startswith(p.upper()) for p in h.subcontractor_employee_prefixes):
        return True
    return _desc_matches(tx, h.subcontractor_description_markers)


# ---------------------------------------------------------------------------
# Summary + evidence
# ---------------------------------------------------------------------------


def _build_summary(
    blocks: list[ContractComplianceBlock],
    cycle_level: list[ContractViolation],
    rules_version: str,
) -> ContractComplianceSummary:
    violations_by_severity: dict[Severity, int] = {"hard": 0, "soft": 0, "info": 0}
    codes: set[str] = set()
    pass_count = 0

    for b in blocks:
        if b.status == "PASS":
            pass_count += 1
        for v in b.violations:
            violations_by_severity[v.severity] = (
                violations_by_severity.get(v.severity, 0) + 1
            )
            codes.add(v.code)

    for v in cycle_level:
        violations_by_severity[v.severity] = (
            violations_by_severity.get(v.severity, 0) + 1
        )
        codes.add(v.code)

    return ContractComplianceSummary(
        contract_rules_version=rules_version,
        total_txs_checked=len(blocks),
        pass_count=pass_count,
        violations=violations_by_severity,
        violation_codes_present=sorted(codes),
    )


def _write_evidence(
    report: ContractComplianceReport, evidence: EvidenceWriter
) -> None:
    """One CONTRACT_CHECKED event per TX + one cycle-level event (blueprint §7/§13)."""
    for block in report.per_tx:
        evidence.append(
            EvidenceEvent(
                tx_id=block.tx_id,
                actor="contract_compliance",
                event="CONTRACT_CHECKED",
                payload={
                    "status": block.status,
                    "violation_count": len(block.violations),
                    "contract_compliance": block.model_dump(mode="json"),
                },
            )
        )

    cycle_key = EvidenceWriter.cycle_key(report.cycle)
    evidence.append(
        EvidenceEvent(
            tx_id=cycle_key,
            actor="contract_compliance",
            event="CONTRACT_CHECKED",
            payload={
                "cycle": report.cycle,
                "contract_rules_version": report.contract_rules_version,
                "cycle_level_violations": [
                    v.model_dump(mode="json") for v in report.cycle_level_violations
                ],
                "summary": report.summary.model_dump(mode="json"),
            },
        )
    )
