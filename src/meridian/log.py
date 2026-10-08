"""Operational JSON logging via structlog.

Blueprint §13: there are two log streams. This module owns the *operational*
stream — "start/finish of each stage, counts, errors, timings" — written to
`local/logs/meridian.jsonl` as newline-delimited JSON for Datadog/SRE.

The *evidence* stream (per-unit append-only audit JSONL) lives in
`evidence.py` and is deliberately kept separate.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import structlog


_CONFIGURED = False


def configure_logging(log_file: Path, level: str = "INFO") -> None:
    """Configure structlog once per process.

    Writes JSON lines to `log_file` AND mirrors a human-readable rendering to
    stderr so CLI runs show live progress.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_file.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # stdlib logging feeds both handlers; structlog's processors render.
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(numeric_level)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    # Clear any existing handlers (e.g. from a prior configure call under test).
    root.handlers = []
    root.addHandler(file_handler)
    root.addHandler(stderr_handler)
    root.setLevel(numeric_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: str | None = None, **initial_values: Any) -> structlog.stdlib.BoundLogger:
    """Return a bound structlog logger. Values become part of every emitted event."""
    logger = structlog.get_logger(name) if name else structlog.get_logger()
    if initial_values:
        logger = logger.bind(**initial_values)
    return logger
