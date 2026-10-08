"""Exception Emitter — deterministic stage (reconciliation-flow.md §5.3).

Reads the two upstream artefacts (SAP ingest + contract compliance) and
categorises every `SAPTransaction` into exactly one of two buckets:

  * `AUTO_PASS_SAP_INTERNAL` — SAP-side clean (no hold, no contract violation,
    no structural flag). Written to `local/auto_pass/<cycle>.json`.
  * `ExceptionCandidate`     — anything else; carries a typed `codes[]` list
    with the reasons triage must look at. Written to
    `local/exceptions/<cycle>.json`.

Codes are additive — a single TX can carry several (e.g. a held
subcontractor TX with a receipt reference AND a compliance violation lands
with SAP_HOLD + BACKUP_REF_PRESENT_NEEDS_MATCH + SUBCONTRACTOR_MARKUP_MISSING).
The emitter never prioritises; triage's Confidence Router owns that call.

Pipeline (per §5.3):
  1. Load cached `SapIngestResult` and `ContractComplianceReport` from disk.
  2. Compute cycle modal currency (for FOREIGN_CURRENCY detection).
  3. For each TX, build its code list from:
       - the per-TX contract-compliance block,
       - SAP_HOLD if `hold_flag == true`,
       - BACKUP_REF_PRESENT_NEEDS_MATCH if `backup_ref` is set,
       - FOREIGN_CURRENCY if the TX currency differs from the cycle modal.
     Empty code list → auto-pass; otherwise → exception candidate.
  4. Persist both buckets at `local/auto_pass/<cycle>.json` and
     `local/exceptions/<cycle>.json`.
  5. Append `EXCEPTION_EMITTED` evidence events (per TX + one cycle-level).

Idempotency (blueprint §12): cache key = SHA-256 of
`source_hash || rules_version || emitter_logic_version`. Both bucket files
must exist AND encode that key to short-circuit.

Node contract (blueprint §5):
  * `do_emit(sap_ingest, compliance_report, *, force) -> (auto_pass, exceptions, fresh)`.
  * `node(state) -> state` — the LangGraph wrapper.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import (
    ExceptionEmitterConfig,
    PipelineConfig,
    load_agent_config,
    load_pipeline_config,
)
from ..contracts import (
    AutoPassBucket,
    AutoPassRecord,
    ContractComplianceReport,
    ContractViolation,
    CycleHeaderRef,
    ExceptionBucket,
    ExceptionBucketCycleContext,
    ExceptionCandidate,
    ExceptionEmitterSummary,
    SAPTransaction,
    SapIngestResult,
)
from ..evidence import EvidenceEvent, EvidenceWriter
from ..log import get_logger


_log = get_logger("exception_emitter")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def do_emit(
    sap_ingest: SapIngestResult | None = None,
    compliance_report: ContractComplianceReport | None = None,
    *,
    force: bool = False,
    pipeline_cfg: PipelineConfig | None = None,
    agent_cfg: ExceptionEmitterConfig | None = None,
) -> tuple[AutoPassBucket, ExceptionBucket, bool]:
    """Run the Exception Emitter and return (auto_pass, exceptions, fresh).

    `fresh=False` means both cached buckets were reused (blueprint §12).
    """
    pipeline_cfg = pipeline_cfg or load_pipeline_config()
    agent_cfg = agent_cfg or load_agent_config(
        "exception_emitter", ExceptionEmitterConfig
    )

    sap_ingest = sap_ingest or _load_sap_ingest(pipeline_cfg)
    compliance_report = compliance_report or _load_compliance(pipeline_cfg)

    cycle = sap_ingest.cycle_header.cycle
    auto_pass_path = pipeline_cfg.auto_pass_dir / f"{cycle}.json"
    exceptions_path = pipeline_cfg.exceptions_dir / f"{cycle}.json"
    evidence = EvidenceWriter(pipeline_cfg.evidence_dir)

    cache_key = _cache_key(sap_ingest, compliance_report, agent_cfg)

    # ---- 1. Cached hit? (idempotency per blueprint §12) ------------------
    if not force and auto_pass_path.exists() and exceptions_path.exists():
        cached = _load_cached_buckets(auto_pass_path, exceptions_path)
        if cached is not None:
            cached_ap, cached_ex = cached
            if (
                cached_ap.cycle_header_ref.source_hash
                == sap_ingest.cycle_header.source_hash
                and cached_ap.cycle_header_ref.contract_rules_version
                == compliance_report.contract_rules_version
                and cached_ex.cycle_header_ref.source_hash
                == sap_ingest.cycle_header.source_hash
                and cached_ex.cycle_header_ref.contract_rules_version
                == compliance_report.contract_rules_version
            ):
                _log.info(
                    "exception_emit_cached",
                    cycle=cycle,
                    auto_pass=cached_ap.summary.auto_pass_count,
                    exceptions=cached_ex.summary.exception_count,
                    auto_pass_artefact=str(auto_pass_path),
                    exceptions_artefact=str(exceptions_path),
                )
                return cached_ap, cached_ex, False
            _log.info(
                "exception_emit_cache_invalid_upstream_bumped",
                cycle=cycle,
                cached_source_hash=cached_ap.cycle_header_ref.source_hash[:16],
                current_source_hash=sap_ingest.cycle_header.source_hash[:16],
                cached_rules_version=cached_ap.cycle_header_ref.contract_rules_version,
                current_rules_version=compliance_report.contract_rules_version,
            )

    # ---- 2–4. Do the work ------------------------------------------------
    emitted_at = datetime.now(timezone.utc)

    cycle_modal_currency = _modal_currency(sap_ingest.transactions)
    compliance_by_tx = {b.tx_id: b for b in compliance_report.per_tx}

    auto_pass_records: list[AutoPassRecord] = []
    candidates: list[ExceptionCandidate] = []

    for tx in sap_ingest.transactions:
        codes: list[str] = []
        violations: list[ContractViolation] = []

        # Contract-compliance codes (echoed verbatim from §5.2).
        block = compliance_by_tx.get(tx.tx_id)
        if block is not None and block.violations:
            violations = list(block.violations)
            for v in block.violations:
                if v.code not in codes:
                    codes.append(v.code)

        # SAP-side code.
        if tx.hold_flag:
            if "SAP_HOLD" not in codes:
                codes.append("SAP_HOLD")

        # Structural codes.
        if (
            agent_cfg.structural_codes.enable_backup_ref_match
            and tx.backup_ref
        ):
            if "BACKUP_REF_PRESENT_NEEDS_MATCH" not in codes:
                codes.append("BACKUP_REF_PRESENT_NEEDS_MATCH")

        if (
            agent_cfg.structural_codes.enable_foreign_currency
            and cycle_modal_currency is not None
            and tx.currency
            and tx.currency != cycle_modal_currency
        ):
            if "FOREIGN_CURRENCY" not in codes:
                codes.append("FOREIGN_CURRENCY")

        if not codes:
            auto_pass_records.append(
                AutoPassRecord(
                    tx_id=tx.tx_id,
                    project_id=tx.project_id,
                    cycle=cycle,
                    amount=tx.amount,
                    currency=tx.currency,
                )
            )
            continue

        candidate_id = _candidate_id(
            prefix=agent_cfg.candidate_id_prefix,
            cycle=cycle,
            tx_id=tx.tx_id,
            seq=len(candidates) + 1,
        )
        candidates.append(
            ExceptionCandidate(
                candidate_id=candidate_id,
                tx_id=tx.tx_id,
                sap_transaction_ref=tx.tx_id,
                codes=codes,
                contract_violations=violations,
                hold_flag=tx.hold_flag,
                hold_reason_raw=tx.hold_reason_raw,
                backup_ref=tx.backup_ref,
                amount=tx.amount,
                currency=tx.currency,
                cycle=cycle,
                project_id=tx.project_id,
                emitted_at=emitted_at,
            )
        )

    summary = _build_summary(
        total_txs=len(sap_ingest.transactions),
        auto_pass=auto_pass_records,
        candidates=candidates,
    )

    header_ref = CycleHeaderRef(
        project_id=sap_ingest.cycle_header.project_id,
        cycle=cycle,
        source_hash=sap_ingest.cycle_header.source_hash,
        contract_rules_version=compliance_report.contract_rules_version,
    )

    auto_pass_bucket = AutoPassBucket(
        cycle=cycle,
        cycle_header_ref=header_ref,
        records=auto_pass_records,
        summary=summary,
        emitted_at=emitted_at,
    )

    exception_bucket = ExceptionBucket(
        cycle=cycle,
        cycle_header_ref=header_ref,
        candidates=candidates,
        cycle_context=ExceptionBucketCycleContext(
            cycle_anomalies=list(sap_ingest.anomalies),
            cycle_level_violations=list(compliance_report.cycle_level_violations),
            contract_compliance_summary=compliance_report.summary,
        ),
        summary=summary,
        emitted_at=emitted_at,
    )

    # ---- 5. Persist artefacts + evidence stream --------------------------
    auto_pass_path.parent.mkdir(parents=True, exist_ok=True)
    auto_pass_path.write_text(
        auto_pass_bucket.model_dump_json(indent=2), encoding="utf-8"
    )
    exceptions_path.parent.mkdir(parents=True, exist_ok=True)
    exceptions_path.write_text(
        exception_bucket.model_dump_json(indent=2), encoding="utf-8"
    )

    _write_evidence(
        auto_pass_bucket=auto_pass_bucket,
        exception_bucket=exception_bucket,
        evidence=evidence,
    )

    _log.info(
        "exception_emit_done",
        cycle=cycle,
        total_txs=summary.total_txs,
        auto_pass=summary.auto_pass_count,
        exceptions=summary.exception_count,
        codes_present=summary.codes_present,
        cache_key=cache_key[:16],
        auto_pass_artefact=str(auto_pass_path),
        exceptions_artefact=str(exceptions_path),
    )
    return auto_pass_bucket, exception_bucket, True


def node(state: Any) -> Any:
    """LangGraph node wrapper.

    Reads `state.sap_ingest` + `state.contract_compliance`; writes
    `state.auto_pass`, `state.exceptions`, `state.exception_emitter_fresh`.
    """
    sap_ingest = getattr(state, "sap_ingest", None)
    compliance = getattr(state, "contract_compliance", None)
    if sap_ingest is None:
        state.errors.append("exception_emitter: no sap_ingest on state")
        return state
    if compliance is None:
        state.errors.append("exception_emitter: no contract_compliance on state")
        return state

    force = bool(getattr(state, "force", False))
    auto_pass_bucket, exception_bucket, fresh = do_emit(
        sap_ingest=sap_ingest,
        compliance_report=compliance,
        force=force,
    )
    state.auto_pass = auto_pass_bucket
    state.exceptions = exception_bucket
    state.exception_emitter_fresh = fresh
    return state


# ---------------------------------------------------------------------------
# Cache key + artefact loaders
# ---------------------------------------------------------------------------


def _cache_key(
    sap_ingest: SapIngestResult,
    compliance_report: ContractComplianceReport,
    agent_cfg: ExceptionEmitterConfig,
) -> str:
    """SHA-256 of (source_hash || rules_version || emitter_logic_version).

    Shields the bucket artefacts from upstream data drift AND from silent
    changes to the categorisation rule in this module.
    """
    h = hashlib.sha256()
    h.update(sap_ingest.cycle_header.source_hash.encode("utf-8"))
    h.update(b"\0")
    h.update(compliance_report.contract_rules_version.encode("utf-8"))
    h.update(b"\0")
    h.update(agent_cfg.emitter_logic_version.encode("utf-8"))
    return h.hexdigest()


def _load_sap_ingest(cfg: PipelineConfig) -> SapIngestResult:
    path = cfg.sap_ingested_dir / f"{cfg.cycle}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No SAP ingest artefact for cycle {cfg.cycle} at {path}. "
            "Run `python -m meridian ingest` first."
        )
    return SapIngestResult.model_validate_json(path.read_text("utf-8"))


def _load_compliance(cfg: PipelineConfig) -> ContractComplianceReport:
    path = cfg.contract_compliance_dir / f"{cfg.cycle}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No contract-compliance artefact for cycle {cfg.cycle} at {path}. "
            "Run `python -m meridian check` first."
        )
    return ContractComplianceReport.model_validate_json(path.read_text("utf-8"))


def _load_cached_buckets(
    auto_pass_path: Path, exceptions_path: Path
) -> tuple[AutoPassBucket, ExceptionBucket] | None:
    """Return the two cached buckets, or None if either is malformed."""
    try:
        ap = AutoPassBucket.model_validate_json(auto_pass_path.read_text("utf-8"))
        ex = ExceptionBucket.model_validate_json(
            exceptions_path.read_text("utf-8")
        )
        return ap, ex
    except (ValidationError, ValueError) as exc:
        _log.warning(
            "exception_emit_cache_invalid_recomputing",
            auto_pass_artefact=str(auto_pass_path),
            exceptions_artefact=str(exceptions_path),
            error=str(exc),
        )
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _modal_currency(txs: list[SAPTransaction]) -> str | None:
    """Modal currency across the TX stream; None if the stream has no currency."""
    currencies = [t.currency for t in txs if t.currency]
    if not currencies:
        return None
    return Counter(currencies).most_common(1)[0][0]


def _candidate_id(*, prefix: str, cycle: str, tx_id: str, seq: int) -> str:
    """Deterministic candidate id: `<prefix>-<cycle>-<tx_short>-<seq:02d>`.

    `tx_short` keeps the last two hyphen-delimited groups of `tx_id` so a
    `TX-2026-04-0044` collapses to `04-0044`. If the tx_id has fewer groups,
    the whole thing is used.
    """
    parts = tx_id.split("-")
    tx_short = "-".join(parts[-2:]) if len(parts) >= 2 else tx_id
    return f"{prefix}-{cycle}-{tx_short}-{seq:02d}"


def _build_summary(
    *,
    total_txs: int,
    auto_pass: list[AutoPassRecord],
    candidates: list[ExceptionCandidate],
) -> ExceptionEmitterSummary:
    codes_by_count: dict[str, int] = {}
    for c in candidates:
        for code in c.codes:
            codes_by_count[code] = codes_by_count.get(code, 0) + 1
    codes_present = sorted(codes_by_count.keys())
    return ExceptionEmitterSummary(
        total_txs=total_txs,
        auto_pass_count=len(auto_pass),
        exception_count=len(candidates),
        codes_present=codes_present,
        codes_by_count=dict(sorted(codes_by_count.items())),
    )


def _write_evidence(
    *,
    auto_pass_bucket: AutoPassBucket,
    exception_bucket: ExceptionBucket,
    evidence: EvidenceWriter,
) -> None:
    """One EXCEPTION_EMITTED event per TX + one cycle-level event (blueprint §7/§13)."""
    for record in auto_pass_bucket.records:
        evidence.append(
            EvidenceEvent(
                tx_id=record.tx_id,
                actor="exception_emitter",
                event="EXCEPTION_EMITTED",
                payload={
                    "bucket": "auto_pass",
                    "reason": record.reason,
                    "record": record.model_dump(mode="json"),
                },
            )
        )

    for candidate in exception_bucket.candidates:
        evidence.append(
            EvidenceEvent(
                tx_id=candidate.tx_id,
                actor="exception_emitter",
                event="EXCEPTION_EMITTED",
                payload={
                    "bucket": "exception",
                    "codes": candidate.codes,
                    "candidate": candidate.model_dump(mode="json"),
                },
            )
        )

    cycle_key = EvidenceWriter.cycle_key(auto_pass_bucket.cycle)
    evidence.append(
        EvidenceEvent(
            tx_id=cycle_key,
            actor="exception_emitter",
            event="EXCEPTION_EMITTED",
            payload={
                "cycle": auto_pass_bucket.cycle,
                "cycle_header_ref": auto_pass_bucket.cycle_header_ref.model_dump(
                    mode="json"
                ),
                "summary": auto_pass_bucket.summary.model_dump(mode="json"),
                "cycle_context": exception_bucket.cycle_context.model_dump(
                    mode="json"
                ),
            },
        )
    )
