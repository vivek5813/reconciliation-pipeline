"""Pydantic domain contracts (DTOs).

Every piece of data that crosses a boundary in this pipeline is modeled here.
Keep the shapes stable — the output contract of each stage is the input contract
of the next (tech-architecture-flow.md §2 principle 9: "seams, not silos").

The SAPTransaction shape mirrors reconciliation-flow.md §5.1 so that when a
future unbilled-CSV ingestor is added, downstream stages don't need to change.
Timecard-only enrichment fields are tacked on as optional extras.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Core SAP transaction record
# ---------------------------------------------------------------------------

TxType = Literal["LABOR", "EXPENSE"]


class SAPTransaction(BaseModel):
    """One row of SAP ground truth for a billing cycle.

    Fields follow the shape documented in reconciliation-flow.md §5.1. Monetary
    fields (`rate`, `amount`, `currency`) are optional because the timecards
    source does not carry them; the contract-compliance stage will skip
    rate/amount checks on TXs where they are None.
    """

    model_config = ConfigDict(extra="forbid")

    # Primary key + routing fields
    tx_id: str
    project_id: str
    task_code: Optional[str] = None
    date: date
    type: TxType

    # Who / what
    employee_id: Optional[str] = None
    role_code: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None

    # Quantities
    quantity: Optional[float] = None
    unit: Optional[str] = None
    rate: Optional[float] = None
    amount: Optional[float] = None
    currency: Optional[str] = None

    # Classification (unbilled-tx extract carries this per row; checker also
    # cross-validates against ContractRules.classification_code at cycle scope).
    classification: Optional[str] = None

    # Hold + backup
    hold_flag: bool = False
    hold_reason_raw: Optional[str] = None
    backup_ref: Optional[str] = None
    note: Optional[str] = None

    # ---- Timecard-source enrichment (optional; absent when sourced from unbilled) ----
    employee_name: Optional[str] = None
    week_ending: Optional[date] = None
    submitted_date: Optional[date] = None
    approver_id: Optional[str] = None
    approver_name: Optional[str] = None
    approval_date: Optional[date] = None
    approval_status: Optional[str] = None
    source_system: Literal["TIMECARDS", "UNBILLED"] = "UNBILLED"


# ---------------------------------------------------------------------------
# Cycle-level artefacts
# ---------------------------------------------------------------------------


class CycleHeader(BaseModel):
    """Cycle-scope summary assembled from the TX stream.

    Produced by §5.1 step 3 of the SAP Ingestor pipeline. Downstream the
    Exception Emitter and Contract Compliance Checker attach cycle-level
    verdicts (e.g. CLASSIFICATION_CODE_MISMATCH) to this header.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    cycle: str  # year-month, e.g. "2026-04"
    currency: Optional[str] = None
    source_filename: str
    source_hash: str  # SHA-256 hex of the raw source file; drives idempotency

    tx_count: int = 0
    labour_tx_count: int = 0
    expense_tx_count: int = 0

    total_labour_hours: float = 0.0

    held_item_count: int = 0
    held_item_hours: float = 0.0
    held_item_amount: float = 0.0

    # Section subtotals (populated when amount is present). Keyed by TX type /
    # category depending on availability in the source.
    section_subtotals: dict[str, float] = Field(default_factory=dict)
    grand_total: Optional[float] = None

    # Cycle-level warnings surfaced by the ingestor (not blocking).
    flags: list[str] = Field(default_factory=list)


class CycleAnomaly(BaseModel):
    """A cycle-scope data quirk the ingestor noticed but did not fail on.

    Severity semantics:
      - "info"    — informational, not actionable by itself
      - "warning" — triage should look; does not block the pipeline
      - "error"   — blocks a cycle-level operation (none currently)
    """

    model_config = ConfigDict(extra="forbid")

    code: str  # e.g. "ENTRY_DATE_OUT_OF_CYCLE", "EMPLOYEE_ALL_HELD"
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    scope: Literal["cycle", "employee", "tx"] = "cycle"
    affected_tx_ids: list[str] = Field(default_factory=list)
    detail: dict[str, Any] = Field(default_factory=dict)


class IngestError(BaseModel):
    """A single row the ingestor could not accept into the TX stream.

    Rows failing mandatory-field checks or duplicate-key detection are emitted
    here (per §5.1 step 2) and excluded from the downstream pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    row_number: int  # 1-indexed, excluding header
    code: Literal[
        "MISSING_MANDATORY_FIELD",
        "DUPLICATE_PRIMARY_KEY",
        "UNPARSEABLE_FIELD",
    ]
    message: str
    row_snapshot: dict[str, str] = Field(default_factory=dict)


class SapIngestResult(BaseModel):
    """Full artefact written by the SAP Ingestor stage.

    Persisted at `local/sap_ingested/<cycle>.json` and consumed by downstream
    stages (contract compliance, exception emitter). This is the stable
    hand-off contract.
    """

    model_config = ConfigDict(extra="forbid")

    cycle_header: CycleHeader
    transactions: list[SAPTransaction] = Field(default_factory=list)
    anomalies: list[CycleAnomaly] = Field(default_factory=list)
    ingest_errors: list[IngestError] = Field(default_factory=list)

    ingested_at: datetime
    contract_rules_version: Optional[str] = None  # populated by a future stage


# ---------------------------------------------------------------------------
# Contract rules (hand-encoded from contract-001.md for the hackathon slice)
# ---------------------------------------------------------------------------

Severity = Literal["hard", "soft", "info"]


class ExpenseRules(BaseModel):
    """Section-4 reimbursable-expense limits from contract-001.md."""

    model_config = ConfigDict(extra="forbid")

    lodging_cap_metro_usd: float
    lodging_cap_other_usd: float
    meal_cap_usd_per_day: float
    per_diem_usd_per_day: float
    per_diem_stackable_with_meal: bool = False
    receipt_threshold_usd: float
    # Policy enums per §4 of the contract. Not currently acted on by code paths
    # beyond the three dedicated checks (ALCOHOL_LINE, PERSONAL_ITEM,
    # ENTERTAINMENT_NEEDS_APPROVAL) — kept here so the YAML stays the single
    # source of truth about *what* the contract says.
    alcohol: Literal["NOT_REIMBURSABLE", "ALLOWED"] = "NOT_REIMBURSABLE"
    personal_items: Literal["NOT_REIMBURSABLE", "ALLOWED"] = "NOT_REIMBURSABLE"
    entertainment: Literal["REQUIRES_PL_APPROVAL", "ALLOWED", "NOT_REIMBURSABLE"] = (
        "REQUIRES_PL_APPROVAL"
    )


class SapNote(BaseModel):
    """One free-text SAP note from contract-001.md §9 that this slice honours
    structurally. Only `PRIN_CAP_PCT` is machine-enforced today."""

    model_config = ConfigDict(extra="forbid")

    rule: str  # e.g. "PRIN_CAP_PCT"
    value: float  # e.g. 5 (percent)
    scope: str  # e.g. "monthly_hours"
    source_date: str  # e.g. "2025-02"
    overridable: bool = True


class ComplianceHeuristics(BaseModel):
    """Knobs for the ambiguous §5.2 checks (keyword lists, trip grouping,
    lodging-metro-vs-other default). Each one maps to an open question flagged
    in reconciliation-flow.md §10.
    """

    model_config = ConfigDict(extra="forbid")

    # Lodging tier — the unbilled extract has no city column, so pick a default.
    # Allowed: "metro" | "other" (per task-code overrides can be added later).
    lodging_default_tier: Literal["metro", "other"] = "other"

    # Trip grouping policy for TRAVEL_CAP_EXCEEDED.
    #   "per_tx" — flag any single travel-time TX whose quantity exceeds the cap.
    # Full employee+date-proximity grouping is deferred (§10 open question).
    trip_grouping: Literal["per_tx"] = "per_tx"

    # Keyword lists — case-insensitive substring match against TX.description.
    alcohol_keywords: list[str] = Field(default_factory=list)
    personal_item_keywords: list[str] = Field(default_factory=list)
    entertainment_keywords: list[str] = Field(default_factory=list)
    per_diem_description_markers: list[str] = Field(default_factory=list)
    lodging_description_markers: list[str] = Field(default_factory=list)
    meal_description_markers: list[str] = Field(default_factory=list)
    travel_description_markers: list[str] = Field(default_factory=list)
    subcontractor_description_markers: list[str] = Field(default_factory=list)
    receipt_missing_markers: list[str] = Field(default_factory=list)

    # Units for which receipts are explicitly waived by the contract (§4).
    receipt_waived_units: list[str] = Field(default_factory=lambda: ["MI", "DAY"])

    # Vendor-id prefixes that mark a transaction as a subcontractor pass-through.
    subcontractor_employee_prefixes: list[str] = Field(default_factory=lambda: ["SUB"])

    # Tolerance (USD) when comparing a markup sibling TX to the expected
    # markup. Shields the check from rounding noise in the SAP extract.
    markup_match_tolerance_usd: float = 0.01

    # Tolerance (USD) for rate comparisons (defends against float dust).
    rate_match_tolerance_usd: float = 0.005


class ContractRules(BaseModel):
    """Structured representation of contract-001.md §3–§5 (plus the §9
    machine-readable SAP notes). The §5.2 checker treats this as its single
    source of truth about *what the contract says*."""

    model_config = ConfigDict(extra="forbid")

    contract_id: str  # e.g. "MSA-NS-2024-0418"
    project_id: str  # e.g. "PRJ-NS-7421"
    currency: str  # e.g. "USD"
    classification_code: str  # §5 invoicing — e.g. "STD-TM-NA-CIVIC"

    role_rates: dict[str, float]  # §3 — e.g. {"ENG1": 145, ...}

    travel_rate_factor: float  # §3 — 0.5 (50% of role rate)
    travel_cap_hours_per_direction: float  # §3 — 8 h per traveller per direction
    subcontractor_markup_pct: float  # §3 — 8 (%)
    mileage_rate_usd_per_mile: float  # §4 — knob, prevailing federal rate

    expense_rules: ExpenseRules
    sap_notes: list[SapNote] = Field(default_factory=list)
    heuristics: ComplianceHeuristics = Field(default_factory=ComplianceHeuristics)

    rules_version: str  # e.g. "MSA-NS-2024-0418@2024-09-01"


# ---------------------------------------------------------------------------
# Contract Compliance Checker outputs (§5.2)
# ---------------------------------------------------------------------------


class ContractViolation(BaseModel):
    """One typed violation attached to either a transaction or the cycle header.

    Shape mirrors the §5.2 output contract exactly so the downstream
    Exception Emitter and triage slice can consume it without re-interpretation.
    """

    model_config = ConfigDict(extra="forbid")

    code: str  # e.g. "RATE_MISMATCH"
    severity: Severity
    rule_citation: str  # e.g. "contract-001.md §3 — rate table"
    detail: str
    expected: Optional[float] = None
    actual: Optional[float] = None
    scope: Literal["tx", "cycle"] = "tx"
    tx_id: Optional[str] = None  # populated for scope="tx" violations


class ContractComplianceBlock(BaseModel):
    """Per-TX compliance verdict (attached conceptually to each SAPTransaction)."""

    model_config = ConfigDict(extra="forbid")

    tx_id: str
    status: Literal["PASS", "VIOLATION"]
    violations: list[ContractViolation] = Field(default_factory=list)
    checked_at: datetime
    contract_rules_version: str


class ContractComplianceSummary(BaseModel):
    """Cycle-wide roll-up for the §6 hand-off contract."""

    model_config = ConfigDict(extra="forbid")

    contract_rules_version: str
    total_txs_checked: int
    pass_count: int
    violations: dict[Severity, int] = Field(
        default_factory=lambda: {"hard": 0, "soft": 0, "info": 0}
    )
    violation_codes_present: list[str] = Field(default_factory=list)


class ContractComplianceReport(BaseModel):
    """Full artefact written by the Contract Compliance Checker stage.

    Persisted at `local/contract_compliance/<cycle>.json` and consumed by the
    downstream Exception Emitter.
    """

    model_config = ConfigDict(extra="forbid")

    cycle: str
    contract_rules_version: str
    per_tx: list[ContractComplianceBlock] = Field(default_factory=list)
    cycle_level_violations: list[ContractViolation] = Field(default_factory=list)
    summary: ContractComplianceSummary
    checked_at: datetime


# ---------------------------------------------------------------------------
# Exception Emitter outputs (§5.3) — two buckets handed off to the triage slice
# ---------------------------------------------------------------------------

# Codes carried on an ExceptionCandidate. The emitter never invents codes; it
# echoes contract-compliance violation codes verbatim and adds the three
# structural codes it is responsible for detecting. Kept as a plain `str` set
# in `ExceptionCandidate.codes` so a future compliance code lands here without
# a schema bump.

# SAP-side code (from the Ingestor's hold flag).
ExceptionSapCode = Literal["SAP_HOLD"]

# Structural codes (computed by the emitter itself from Ingestor output).
ExceptionStructuralCode = Literal[
    "BACKUP_REF_PRESENT_NEEDS_MATCH",
    "FOREIGN_CURRENCY",
]


AutoPassReason = Literal["AUTO_PASS_SAP_INTERNAL"]


class ExceptionCandidate(BaseModel):
    """One typed exception needing triage attention (reconciliation-flow.md §5.3).

    A single TX becomes one candidate; `codes` is additive — a TX can carry
    SAP_HOLD + BACKUP_REF_PRESENT_NEEDS_MATCH + a contract violation code all
    at once. The emitter deliberately does not prioritise them; triage's
    Confidence Router owns that call.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    tx_id: str
    sap_transaction_ref: str  # same as tx_id for this slice (future: may differ)
    codes: list[str] = Field(default_factory=list)
    contract_violations: list[ContractViolation] = Field(default_factory=list)
    hold_flag: bool = False
    hold_reason_raw: Optional[str] = None
    backup_ref: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    cycle: str
    project_id: str
    emitted_at: datetime


class AutoPassRecord(BaseModel):
    """One `AUTO_PASS_SAP_INTERNAL` record — SAP-internally clean TX.

    Thin on purpose. The authoritative TX detail lives on the SAP ingest
    artefact; this record is the hand-off that says "triage still runs
    document matching but needs no further SAP-side work" (§5.3).
    """

    model_config = ConfigDict(extra="forbid")

    tx_id: str
    project_id: str
    cycle: str
    amount: Optional[float] = None
    currency: Optional[str] = None
    reason: AutoPassReason = "AUTO_PASS_SAP_INTERNAL"


class CycleHeaderRef(BaseModel):
    """Compact pointer back to the upstream artefacts.

    Embedded on both buckets so an auditor or the downstream triage slice can
    verify which SAP extract + which contract-rules version produced them,
    without reloading every TX record.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: str
    cycle: str
    source_hash: str
    contract_rules_version: str


class ExceptionEmitterSummary(BaseModel):
    """Cycle-wide roll-up written on both buckets for quick inspection."""

    model_config = ConfigDict(extra="forbid")

    total_txs: int
    auto_pass_count: int
    exception_count: int
    codes_present: list[str] = Field(default_factory=list)
    codes_by_count: dict[str, int] = Field(default_factory=dict)


class AutoPassBucket(BaseModel):
    """`local/auto_pass/<cycle>.json` — SAP-side-clean TXs.

    One of the two typed streams handed to the triage slice (§5.3 / §6).
    """

    model_config = ConfigDict(extra="forbid")

    cycle: str
    cycle_header_ref: CycleHeaderRef
    records: list[AutoPassRecord] = Field(default_factory=list)
    summary: ExceptionEmitterSummary
    emitted_at: datetime


class ExceptionBucketCycleContext(BaseModel):
    """Cycle-scope attention markers travelling alongside the per-TX candidates.

    Cycle-level anomalies and violations are not emitted as per-TX candidates
    (per §5.3 — "Cycle-level anomalies are carried on the ReconciledSAPView"),
    but triage still needs them to interpret the exception stream. We embed
    a compact copy here so triage never has to re-fetch the upstream artefacts.
    """

    model_config = ConfigDict(extra="forbid")

    cycle_anomalies: list[CycleAnomaly] = Field(default_factory=list)
    cycle_level_violations: list[ContractViolation] = Field(default_factory=list)
    contract_compliance_summary: ContractComplianceSummary


class ExceptionBucket(BaseModel):
    """`local/exceptions/<cycle>.json` — typed `ExceptionCandidate` stream.

    Second of the two typed streams handed to the triage slice (§5.3 / §6).
    """

    model_config = ConfigDict(extra="forbid")

    cycle: str
    cycle_header_ref: CycleHeaderRef
    candidates: list[ExceptionCandidate] = Field(default_factory=list)
    cycle_context: ExceptionBucketCycleContext
    summary: ExceptionEmitterSummary
    emitted_at: datetime


# ---------------------------------------------------------------------------
# Evidence event (shared across stages — operational-audit append log)
# ---------------------------------------------------------------------------


class EvidenceEventModel(BaseModel):
    """Typed companion to the raw EvidenceEvent dataclass in evidence.py.

    Exists so that call-sites which already hold Pydantic data can build an
    event with validation. The on-disk JSONL shape is identical.
    """

    model_config = ConfigDict(extra="forbid")

    tx_id: str  # or "_cycle_<cycle>" for cycle-level events
    actor: str  # e.g. "sap_ingestor"
    event: str  # e.g. "SAP_INGESTED", "CYCLE_INGESTED"
    payload: dict[str, Any] = Field(default_factory=dict)
