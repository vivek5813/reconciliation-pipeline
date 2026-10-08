"""Configuration loading.

Two layers:
  * PipelineConfig — one file per project (config/pipeline.yaml): paths, cycle, logging.
  * Per-agent configs — one YAML per agent under config/agents/<name>.yaml.
    Each agent defines its own Pydantic class; `load_agent_config(name, cls)`
    is the generic loader.

Blueprint §6: "The model name lives here, nowhere else in the repo." For
deterministic stages (type == "deterministic") there is no model.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Type, TypeVar

import yaml
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Repository root resolution
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def repo_root() -> Path:
    """Return the repository root.

    Walk upward from this file until we find pyproject.toml. Caching keeps the
    lookup cheap for repeated calls.
    """
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: two levels up from src/meridian/config.py → repo root.
    return here.parents[2]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping at the top of {path}, got {type(data).__name__}")
    return data


# ---------------------------------------------------------------------------
# Pipeline-level config
# ---------------------------------------------------------------------------


class PipelinePaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: str
    local_dir: str = "local"
    raw_dir: str = "local/raw"
    sap_ingested_dir: str = "local/sap_ingested"
    contract_compliance_dir: str = "local/contract_compliance"
    auto_pass_dir: str = "local/auto_pass"
    exceptions_dir: str = "local/exceptions"
    evidence_dir: str = "local/evidence"
    logs_dir: str = "local/logs"


class PipelineLogging(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: str = "INFO"
    file: str = "local/logs/meridian.jsonl"


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cycle: str
    paths: PipelinePaths
    logging: PipelineLogging = Field(default_factory=PipelineLogging)

    # --- Helpers (resolve relative paths against the repo root) ---

    def resolve(self, relative: str) -> Path:
        """Resolve a config-relative path to an absolute Path."""
        p = Path(relative)
        if p.is_absolute():
            return p
        return repo_root() / p

    @property
    def data_dir(self) -> Path:
        return self.resolve(self.paths.data_dir)

    @property
    def sap_ingested_dir(self) -> Path:
        return self.resolve(self.paths.sap_ingested_dir)

    @property
    def contract_compliance_dir(self) -> Path:
        return self.resolve(self.paths.contract_compliance_dir)

    @property
    def auto_pass_dir(self) -> Path:
        return self.resolve(self.paths.auto_pass_dir)

    @property
    def exceptions_dir(self) -> Path:
        return self.resolve(self.paths.exceptions_dir)

    @property
    def evidence_dir(self) -> Path:
        return self.resolve(self.paths.evidence_dir)

    @property
    def logs_dir(self) -> Path:
        return self.resolve(self.paths.logs_dir)

    @property
    def log_file(self) -> Path:
        return self.resolve(self.logging.file)


def load_pipeline_config(path: Path | None = None) -> PipelineConfig:
    """Load config/pipeline.yaml."""
    path = path or (repo_root() / "config" / "pipeline.yaml")
    return PipelineConfig.model_validate(_load_yaml(path))


# ---------------------------------------------------------------------------
# Per-agent config (generic loader)
# ---------------------------------------------------------------------------


T = TypeVar("T", bound=BaseModel)


def load_agent_config(name: str, model_cls: Type[T]) -> T:
    """Load `config/agents/<name>.yaml` as the given Pydantic class.

    Pattern per blueprint §6: adding a new agent is "write a Pydantic class →
    write the YAML → done".
    """
    path = repo_root() / "config" / "agents" / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Agent config not found: {path}")
    return model_cls.model_validate(_load_yaml(path))


# ---------------------------------------------------------------------------
# SAP Ingestor config
# ---------------------------------------------------------------------------


class SapIngestorSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str  # relative to pipeline paths.data_dir
    encoding: str = "utf-8"


class SapIngestorConfig(BaseModel):
    """Config contract for the SAP Ingestor agent (deterministic — no model)."""

    model_config = ConfigDict(extra="forbid")

    agent: Literal["sap_ingestor"]
    type: Literal["deterministic"]

    source: SapIngestorSource
    mandatory_fields: list[str] = Field(default_factory=list)
    duplicate_policy: Literal["first_wins", "last_wins", "error"] = "first_wins"
    # Values in the unbilled-tx CSV's `hold_flag` column that denote a true hold.
    hold_flag_true_values: list[str] = Field(
        default_factory=lambda: ["Y", "y", "true", "TRUE", "1"]
    )


# ---------------------------------------------------------------------------
# Contract Compliance Checker config (ContractRules + knobs)
# ---------------------------------------------------------------------------

# Imported lazily to avoid a cycle at import time (contracts imports nothing
# from config, but keeping the import here makes the dependency explicit).
from .contracts import ContractRules  # noqa: E402  (deliberate late import)


class ContractComplianceConfig(BaseModel):
    """Config contract for the Contract Compliance Checker agent.

    Deterministic stage (no model). The entire `ContractRules` object is
    hand-encoded here per reconciliation-flow.md §5.2 — "For the hackathon
    prototype this is hand-encoded; in production it would be produced by a
    future ContractIngestor pre-stage" (§10 open question).
    """

    model_config = ConfigDict(extra="forbid")

    agent: Literal["contract_compliance"]
    type: Literal["deterministic"]

    rules: ContractRules


# ---------------------------------------------------------------------------
# Exception Emitter config (§5.3 — deterministic, no model)
# ---------------------------------------------------------------------------


class ExceptionEmitterStructuralCodes(BaseModel):
    """Toggles for the structural codes the §5.3 emitter can attach to a TX."""

    model_config = ConfigDict(extra="forbid")

    enable_backup_ref_match: bool = True
    enable_foreign_currency: bool = True


class ExceptionEmitterConfig(BaseModel):
    """Config contract for the Exception Emitter agent (deterministic — no model).

    `emitter_logic_version` feeds the idempotency cache key alongside the SAP
    source hash and the contract rules_version. Bump it whenever the
    categorisation rule in `exception_emitter.py` changes so cached buckets
    invalidate on the next run.
    """

    model_config = ConfigDict(extra="forbid")

    agent: Literal["exception_emitter"]
    type: Literal["deterministic"]

    structural_codes: ExceptionEmitterStructuralCodes = Field(
        default_factory=ExceptionEmitterStructuralCodes
    )
    candidate_id_prefix: str = "EC"
    emitter_logic_version: str = "emitter_v1"
