"""Append-only per-unit evidence audit writer.

Blueprint §13: this is the *second* log stream, kept deliberately separate
from operational logs. One file per unit of work (per TX) with one JSONL line
per state transition. Audiences: auditors, analysts, dispute reviewers.

Cycle-level events are written to a special `_cycle_<cycle>.jsonl` file so
they don't pollute any single TX's audit trail.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceEvent:
    """One append-only event in a unit-of-work's audit trail."""

    tx_id: str  # or "_cycle_<cycle>" for cycle-scope events
    actor: str  # e.g. "sap_ingestor"
    event: str  # e.g. "SAP_INGESTED", "CYCLE_INGESTED"
    payload: dict[str, Any] = field(default_factory=dict)

    def to_line(self) -> str:
        return json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "tx_id": self.tx_id,
                "actor": self.actor,
                "event": self.event,
                "payload": self.payload,
            },
            default=str,
            ensure_ascii=False,
        )


class EvidenceWriter:
    """Writes JSONL lines to `<evidence_dir>/<tx_id>.jsonl`. Append-only.

    No deletes, no updates. If a stage runs twice on the same TX, two events
    are written — the audit trail reflects every attempt.
    """

    def __init__(self, evidence_dir: Path) -> None:
        self.evidence_dir = evidence_dir
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, tx_id: str) -> Path:
        # Replace any path-separator characters just in case (defence-in-depth
        # against a malformed tx_id). We never trust an id to be filename-safe.
        safe = tx_id.replace("/", "_").replace("\\", "_")
        return self.evidence_dir / f"{safe}.jsonl"

    def append(self, event: EvidenceEvent) -> None:
        path = self._path(event.tx_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(event.to_line() + "\n")

    def append_many(self, events: list[EvidenceEvent]) -> None:
        for ev in events:
            self.append(ev)

    @staticmethod
    def cycle_key(cycle: str) -> str:
        """Return the pseudo-tx_id used for cycle-scope events."""
        return f"_cycle_{cycle}"
