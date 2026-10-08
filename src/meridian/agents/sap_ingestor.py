"""SAP Ingestor — deterministic stage.

Reads the SAP unbilled-transaction CSV export and produces a typed
`SapIngestResult { CycleHeader, SAPTransaction[], CycleAnomaly[], IngestError[] }`.

Follows reconciliation-flow.md §5.1 — the authoritative SAP source for this
slice is `unbilled-2026-04.csv` (both LABOR and EXPENSE rows, with
rate/amount/currency and per-TX classification code populated). This is the
stream the §5.2 Contract Compliance Checker consumes downstream; the
SAPTransaction output shape is stable so later stages don't change when the
upstream SAP system does.

Pipeline (per §5.1):
  1. CSV parse (stdlib csv.DictReader).
  2. Row validation (mandatory fields, type coercion).  Failures become IngestErrors.
  3. Duplicate-primary-key detection.                    Duplicates become IngestErrors.
  4. CycleHeader assembly (counts, hours, section subtotals, grand total, holds).
  5. Cycle anomaly scan (entry dates outside the cycle, currency mix).
  6. Content-hash idempotency (SHA-256 of the source file).

Node contract (blueprint §5):
  * `do_ingest(csv_path, *, force) -> (SapIngestResult, fresh)` — the lower-level
    helper, usable from the CLI without going through the graph.
  * `node(state) -> state` — the LangGraph wrapper.
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..config import (
    PipelineConfig,
    SapIngestorConfig,
    load_agent_config,
    load_pipeline_config,
)
from ..contracts import (
    CycleAnomaly,
    CycleHeader,
    IngestError,
    SAPTransaction,
    SapIngestResult,
)
from ..evidence import EvidenceEvent, EvidenceWriter
from ..log import get_logger


_log = get_logger("sap_ingestor")


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def do_ingest(
    csv_path: Path | None = None,
    *,
    force: bool = False,
    pipeline_cfg: PipelineConfig | None = None,
    agent_cfg: SapIngestorConfig | None = None,
) -> tuple[SapIngestResult, bool]:
    """Run the SAP Ingestor on `csv_path` and return (result, fresh).

    `fresh=False` means the cached artefact was reused (blueprint §12).
    """
    pipeline_cfg = pipeline_cfg or load_pipeline_config()
    agent_cfg = agent_cfg or load_agent_config("sap_ingestor", SapIngestorConfig)

    csv_path = csv_path or (pipeline_cfg.data_dir / agent_cfg.source.filename)
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"SAP source CSV not found: {csv_path}")

    out_path = pipeline_cfg.sap_ingested_dir / f"{pipeline_cfg.cycle}.json"
    evidence = EvidenceWriter(pipeline_cfg.evidence_dir)

    # ---- 1. Cached hit? (idempotency per blueprint §12) ------------------
    if out_path.exists() and not force:
        try:
            cached = SapIngestResult.model_validate_json(out_path.read_text("utf-8"))
            _log.info(
                "sap_ingest_cached",
                cycle=pipeline_cfg.cycle,
                tx_count=cached.cycle_header.tx_count,
                artefact=str(out_path),
            )
            return cached, False
        except (ValidationError, ValueError) as exc:
            # Cached artefact is malformed → recompute.
            _log.warning(
                "sap_ingest_cache_invalid_recomputing",
                cycle=pipeline_cfg.cycle,
                artefact=str(out_path),
                error=str(exc),
            )

    # ---- 2–6. Do the work -----------------------------------------------
    source_hash = _hash_file(csv_path)
    txs, errors, raw_rows = _parse_rows(csv_path, agent_cfg)

    cycle_header = _build_cycle_header(
        txs,
        cycle=pipeline_cfg.cycle,
        source_filename=str(csv_path.relative_to(pipeline_cfg.data_dir))
        if csv_path.is_relative_to(pipeline_cfg.data_dir)
        else csv_path.name,
        source_hash=source_hash,
    )
    anomalies = _scan_cycle_anomalies(txs, cycle=pipeline_cfg.cycle)

    result = SapIngestResult(
        cycle_header=cycle_header,
        transactions=txs,
        anomalies=anomalies,
        ingest_errors=errors,
        ingested_at=datetime.now(timezone.utc),
    )

    # ---- 7. Persist artefact + evidence stream --------------------------
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")

    _write_evidence(result, evidence, raw_rows)

    _log.info(
        "sap_ingest_done",
        cycle=pipeline_cfg.cycle,
        source=str(csv_path),
        tx_count=cycle_header.tx_count,
        held=cycle_header.held_item_count,
        anomalies=len(anomalies),
        errors=len(errors),
        artefact=str(out_path),
    )
    return result, True


def node(state: Any) -> Any:
    """LangGraph node wrapper. Reads `state.force`; writes `state.sap_ingest`."""
    force = bool(getattr(state, "force", False))
    result, fresh = do_ingest(force=force)
    state.sap_ingest = result
    state.sap_ingest_fresh = fresh
    return state


# ---------------------------------------------------------------------------
# Internals — parsing and validation
# ---------------------------------------------------------------------------

# Field mapping: unbilled-tx CSV column → SAPTransaction attribute.
# Explicit so a reader can diff against reconciliation-flow.md §5.1 at a glance.
_UNBILLED_COLUMNS = (
    "transaction_id",
    "project_id",
    "task_code",
    "transaction_date",
    "type",
    "employee_id",
    "role_code",
    "description",
    "quantity",
    "unit",
    "rate",
    "amount",
    "currency",
    "classification",
    "hold_flag",
    "hold_reason",
    "note",
)

# Markers that extract a backup-document id out of the free-text `note` column.
# e.g. "Receipt: RC-001", "Vendor invoice: VI-002", "Mileage log: ML-001".
_BACKUP_REF_PATTERNS = (
    re.compile(r"Receipt:\s*([A-Z]{2}-\d+)", re.IGNORECASE),
    re.compile(r"Vendor invoice:\s*([A-Z]{2}-\d+)", re.IGNORECASE),
    re.compile(r"Mileage log:\s*([A-Z]{2}-\d+)", re.IGNORECASE),
)


def _parse_rows(
    csv_path: Path,
    cfg: SapIngestorConfig,
) -> tuple[list[SAPTransaction], list[IngestError], list[dict[str, str]]]:
    """Return (transactions, ingest_errors, raw_rows_for_evidence)."""
    txs: list[SAPTransaction] = []
    errors: list[IngestError] = []
    raw_rows: list[dict[str, str]] = []

    seen_ids: dict[str, int] = {}
    hold_true = set(cfg.hold_flag_true_values)

    with csv_path.open("r", encoding=cfg.source.encoding, newline="") as fh:
        reader = csv.DictReader(fh)
        for row_number, row in enumerate(reader, start=1):
            # Strip surrounding whitespace on all values.
            clean = {k: (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            raw_rows.append(clean)

            # (2) Mandatory field check.
            missing = [f for f in cfg.mandatory_fields if not clean.get(f)]
            if missing:
                errors.append(
                    IngestError(
                        row_number=row_number,
                        code="MISSING_MANDATORY_FIELD",
                        message=f"Row missing mandatory field(s): {', '.join(missing)}",
                        row_snapshot=_snapshot(clean),
                    )
                )
                continue

            # (3) Duplicate primary-key check.
            tx_id = clean["transaction_id"]
            if tx_id in seen_ids:
                if cfg.duplicate_policy == "error":
                    errors.append(
                        IngestError(
                            row_number=row_number,
                            code="DUPLICATE_PRIMARY_KEY",
                            message=(
                                f"Duplicate transaction_id {tx_id!r}; first seen at row "
                                f"{seen_ids[tx_id]}."
                            ),
                            row_snapshot=_snapshot(clean),
                        )
                    )
                    continue
                if cfg.duplicate_policy == "first_wins":
                    errors.append(
                        IngestError(
                            row_number=row_number,
                            code="DUPLICATE_PRIMARY_KEY",
                            message=(
                                f"Duplicate transaction_id {tx_id!r} (row "
                                f"{seen_ids[tx_id]} kept, this row dropped)."
                            ),
                            row_snapshot=_snapshot(clean),
                        )
                    )
                    continue
                # last_wins: drop the earlier one from `txs` and continue below.
                txs = [t for t in txs if t.tx_id != tx_id]

            # (type coercion) — build the SAPTransaction.
            try:
                tx = _row_to_transaction(clean, hold_true=hold_true)
            except ValueError as exc:
                errors.append(
                    IngestError(
                        row_number=row_number,
                        code="UNPARSEABLE_FIELD",
                        message=str(exc),
                        row_snapshot=_snapshot(clean),
                    )
                )
                continue

            seen_ids[tx_id] = row_number
            txs.append(tx)

    return txs, errors, raw_rows


def _row_to_transaction(
    row: dict[str, str],
    *,
    hold_true: set[str],
) -> SAPTransaction:
    """Map one cleaned CSV row to a SAPTransaction.

    Raises ValueError on any unparseable field (date, numeric fields, type).
    """
    # ---- Dates --------------------------------------------------------
    try:
        tx_date = date.fromisoformat(row["transaction_date"])
    except ValueError as exc:
        raise ValueError(
            f"Unparseable transaction_date {row.get('transaction_date')!r}: {exc}"
        ) from exc

    # ---- Type ---------------------------------------------------------
    raw_type = (row.get("type") or "").upper()
    if raw_type not in ("LABOR", "EXPENSE"):
        raise ValueError(f"Unknown type {row.get('type')!r} (expected LABOR or EXPENSE)")

    # ---- Numerics (optional – blank-safe) -----------------------------
    quantity = _parse_float_opt(row.get("quantity"), field="quantity")
    rate = _parse_float_opt(row.get("rate"), field="rate")
    amount = _parse_float_opt(row.get("amount"), field="amount")

    # ---- Hold flag + reason ------------------------------------------
    hold_raw = (row.get("hold_flag") or "").strip()
    held = hold_raw in hold_true
    hold_reason_raw = (row.get("hold_reason") or None) if held else None

    # ---- Backup ref: pulled out of free-text `note` ------------------
    note = row.get("note") or None
    backup_ref = _extract_backup_ref(note)

    return SAPTransaction(
        tx_id=row["transaction_id"],
        project_id=row["project_id"],
        task_code=row.get("task_code") or None,
        date=tx_date,
        type=raw_type,  # type: ignore[arg-type]
        employee_id=row.get("employee_id") or None,
        role_code=row.get("role_code") or None,
        description=row.get("description") or None,
        category=None,  # unbilled extract has no explicit category; checker derives from description/unit
        quantity=quantity,
        unit=row.get("unit") or None,
        rate=rate,
        amount=amount,
        currency=row.get("currency") or None,
        classification=row.get("classification") or None,
        hold_flag=held,
        hold_reason_raw=hold_reason_raw,
        backup_ref=backup_ref,
        note=note,
        # Timecard-only enrichment stays None under the unbilled source.
        source_system="UNBILLED",
    )


def _parse_float_opt(value: str | None, *, field: str) -> float | None:
    """Parse an optional float. Empty / None → None; invalid → ValueError."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unparseable {field} {value!r}: {exc}") from exc


def _extract_backup_ref(note: str | None) -> str | None:
    """Return the first backup-document id found in `note`, if any."""
    if not note:
        return None
    for pat in _BACKUP_REF_PATTERNS:
        m = pat.search(note)
        if m:
            return m.group(1).upper()
    return None


def _snapshot(row: dict[str, Any]) -> dict[str, str]:
    """Return a str-only snapshot of a row for IngestError.row_snapshot."""
    return {k: ("" if v is None else str(v)) for k, v in row.items()}


# ---------------------------------------------------------------------------
# Internals — cycle header & anomalies
# ---------------------------------------------------------------------------


def _build_cycle_header(
    txs: list[SAPTransaction],
    *,
    cycle: str,
    source_filename: str,
    source_hash: str,
) -> CycleHeader:
    labour_count = sum(1 for t in txs if t.type == "LABOR")
    expense_count = sum(1 for t in txs if t.type == "EXPENSE")
    total_hours = sum((t.quantity or 0.0) for t in txs if t.type == "LABOR")

    held = [t for t in txs if t.hold_flag]
    held_hours = sum((t.quantity or 0.0) for t in held)
    held_amount = sum((t.amount or 0.0) for t in held)

    # Modal project_id (defensive: the extract may touch >1 project in theory).
    project_id = (
        Counter(t.project_id for t in txs).most_common(1)[0][0] if txs else ""
    )

    # Currency: only populated when the source carries it.
    currencies = {t.currency for t in txs if t.currency}
    currency = next(iter(currencies)) if len(currencies) == 1 else None

    flags: list[str] = []
    if len(currencies) > 1:
        flags.append("CURRENCY_MIX")
    if not txs:
        flags.append("EMPTY_SOURCE")

    # Section subtotals keyed by TX type. The unbilled extract always carries
    # amounts so these are the authoritative figures; LABOR_HOURS is also
    # included for the downstream PRIN-cap check.
    section_subtotals: dict[str, float] = {}
    labour_amount = sum((t.amount or 0.0) for t in txs if t.type == "LABOR")
    if labour_amount:
        section_subtotals["LABOR"] = round(labour_amount, 2)
    expense_amount = sum((t.amount or 0.0) for t in txs if t.type == "EXPENSE")
    if expense_amount:
        section_subtotals["EXPENSE"] = round(expense_amount, 2)
    section_subtotals["LABOR_HOURS"] = round(total_hours, 2)

    grand_total: float | None = None
    if labour_amount or expense_amount:
        grand_total = round(labour_amount + expense_amount, 2)

    return CycleHeader(
        project_id=project_id,
        cycle=cycle,
        currency=currency,
        source_filename=source_filename,
        source_hash=source_hash,
        tx_count=len(txs),
        labour_tx_count=labour_count,
        expense_tx_count=expense_count,
        total_labour_hours=round(total_hours, 2),
        held_item_count=len(held),
        held_item_hours=round(held_hours, 2),
        held_item_amount=round(held_amount, 2),
        section_subtotals=section_subtotals,
        grand_total=grand_total,
        flags=flags,
    )


def _scan_cycle_anomalies(txs: list[SAPTransaction], *, cycle: str) -> list[CycleAnomaly]:
    """Scan for cycle-scope data quirks.

    `E_7702_LABOUR_GAP` from §5.1 is intentionally skipped here — it needs
    cross-reference with the timecards source (which this ingestor is not
    reading) to detect "expense rows but no labour rows for employee X".
    """
    anomalies: list[CycleAnomaly] = []
    if not txs:
        return anomalies

    try:
        cycle_year, cycle_month = (int(part) for part in cycle.split("-", 1))
    except ValueError:
        cycle_year = cycle_month = 0

    # (a) Entry dates falling outside the cycle year-month → potential mis-cycle.
    if cycle_year and cycle_month:
        off_cycle = [
            t for t in txs if (t.date.year, t.date.month) != (cycle_year, cycle_month)
        ]
        if off_cycle:
            anomalies.append(
                CycleAnomaly(
                    code="ENTRY_DATE_OUT_OF_CYCLE",
                    severity="info",
                    scope="cycle",
                    message=(
                        f"{len(off_cycle)} transaction(s) have transaction_date outside "
                        f"cycle {cycle}. Allowed where work spans the cycle boundary; "
                        "triage should confirm."
                    ),
                    affected_tx_ids=[t.tx_id for t in off_cycle],
                    detail={"cycle": cycle},
                )
            )

    # (b) Foreign-currency rows on a cycle whose modal currency differs.
    currencies = [t.currency for t in txs if t.currency]
    if currencies:
        modal = Counter(currencies).most_common(1)[0][0]
        foreign = [t for t in txs if t.currency and t.currency != modal]
        if foreign:
            anomalies.append(
                CycleAnomaly(
                    code="FOREIGN_CURRENCY_PRESENT",
                    severity="warning",
                    scope="cycle",
                    message=(
                        f"{len(foreign)} transaction(s) carry a currency other "
                        f"than the modal cycle currency {modal!r}. Triage must "
                        "confirm the FX treatment before billing."
                    ),
                    affected_tx_ids=[t.tx_id for t in foreign],
                    detail={"modal_currency": modal},
                )
            )

    return anomalies


# ---------------------------------------------------------------------------
# Internals — content hash & evidence
# ---------------------------------------------------------------------------


def _hash_file(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_evidence(
    result: SapIngestResult,
    evidence: EvidenceWriter,
    raw_rows: list[dict[str, str]],
) -> None:
    """Emit one SAP_INGESTED event per TX and one CYCLE_INGESTED event per cycle.

    Rows that failed ingestion get their own evidence line keyed on the row
    number — those have no tx_id but still need an audit trail.
    """
    header = result.cycle_header

    for tx in result.transactions:
        evidence.append(
            EvidenceEvent(
                tx_id=tx.tx_id,
                actor="sap_ingestor",
                event="SAP_INGESTED",
                payload={
                    "cycle": header.cycle,
                    "source_filename": header.source_filename,
                    "source_hash": header.source_hash,
                    "tx": tx.model_dump(mode="json"),
                },
            )
        )

    cycle_key = EvidenceWriter.cycle_key(header.cycle)
    evidence.append(
        EvidenceEvent(
            tx_id=cycle_key,
            actor="sap_ingestor",
            event="CYCLE_INGESTED",
            payload={
                "cycle_header": header.model_dump(mode="json"),
                "anomalies": [a.model_dump(mode="json") for a in result.anomalies],
                "ingest_error_count": len(result.ingest_errors),
            },
        )
    )

    for err in result.ingest_errors:
        evidence.append(
            EvidenceEvent(
                tx_id=cycle_key,
                actor="sap_ingestor",
                event="SAP_INGEST_ERROR",
                payload={"error": err.model_dump(mode="json")},
            )
        )
