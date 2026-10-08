"""LangGraph wiring for the reconciliation pipeline.

Blueprint §8: a single Pydantic PipelineState carries everything through the
graph; nodes mutate it; edges stay explicit. The graph stays flat and gains
nodes incrementally.

Nodes today:
  * `sap_ingestor`        — §5.1 deterministic parse of the unbilled extract.
  * `contract_compliance` — §5.2 deterministic contract-rule validation.
  * `exception_emitter`   — §5.3 deterministic bucket categorisation.

Future nodes drop in by adding them here and chaining the edges — no
restructuring of state or contracts needed.
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from .agents import contract_compliance as contract_compliance_agent
from .agents import exception_emitter as exception_emitter_agent
from .agents import sap_ingestor as sap_ingestor_agent
from .contracts import (
    AutoPassBucket,
    ContractComplianceReport,
    ExceptionBucket,
    SapIngestResult,
)


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------


class PipelineState(BaseModel):
    """Mutable state carried through one pipeline run.

    Fields are optional on construction and populated by their owning node.
    New stages add their output as a new optional field; prior fields are
    never mutated.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Run-level controls
    force: bool = False

    # Stage outputs
    sap_ingest: Optional[SapIngestResult] = None
    sap_ingest_fresh: Optional[bool] = None
    contract_compliance: Optional[ContractComplianceReport] = None
    contract_compliance_fresh: Optional[bool] = None
    auto_pass: Optional[AutoPassBucket] = None
    exceptions: Optional[ExceptionBucket] = None
    exception_emitter_fresh: Optional[bool] = None

    # Operational
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph():
    """Compile the StateGraph for the reconciliation slice."""
    graph = StateGraph(PipelineState)

    graph.add_node("sap_ingestor", sap_ingestor_agent.node)
    graph.add_node("contract_compliance", contract_compliance_agent.node)
    graph.add_node("exception_emitter", exception_emitter_agent.node)

    graph.set_entry_point("sap_ingestor")
    graph.add_edge("sap_ingestor", "contract_compliance")
    graph.add_edge("contract_compliance", "exception_emitter")
    graph.add_edge("exception_emitter", END)

    return graph.compile()


def run_pipeline(*, force: bool = False) -> PipelineState:
    """Run the full pipeline end-to-end once and return the final state."""
    compiled = build_graph()
    initial = PipelineState(force=force)
    # LangGraph's `invoke` returns either a dict or the state model depending
    # on version; normalise back to PipelineState for callers.
    final = compiled.invoke(initial)
    if isinstance(final, PipelineState):
        return final
    return PipelineState.model_validate(final)
