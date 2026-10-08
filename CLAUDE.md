# Meridian Atlas Partners — AI Agent Guidance

Agentic document-extraction pipeline for a professional-services billing workflow. Design: [documentation/document-extraction-flow_plan.md](documentation/document-extraction-flow_plan.md).

## Tech stack

- **Python 3.11+**
- **Anthropic** (`anthropic`) — LLM provider; model per agent in YAML
- **LangGraph** — pipeline orchestration (`StateGraph`, one graph per document)
- **Pydantic v2** — domain contracts, agent configs, LLM-output validation
- **Typer** — CLI (`python -m meridian ...`)
- **structlog** — JSON operational logs
- **PyYAML** — config loading
- Filesystem for state (`local/raw`, `local/layout`, `local/evidence`); swap for object storage + SQLite later.

## Layout

```
config/
  pipeline.yaml                 # paths, cycle, logging
  agents/<agent>.yaml           # one file per agent; `model:` lives here
src/meridian/
  cli.py        contracts.py    config.py    log.py    evidence.py
  graph.py                      # LangGraph wiring
  agents/
    intake.py                   # deterministic
    layout_extractor.py         # Claude
data/.../documents/             # the "SharePoint" drop folder (markdown samples)
local/                          # gitignored runtime output
```

## Conventions

- **One YAML config per agent** under `config/agents/`. Every LLM agent has its own `model:` — swap models there, never in code.
- **Each agent is a LangGraph node** exposing `node(state) -> state`. Add new nodes in `src/meridian/agents/` and wire them in `graph.py`.
- **Pydantic everywhere** data crosses a boundary (YAML → config, LLM JSON → `LayoutExtract`, state → `PipelineState`).
- **Idempotent**: re-running the pipeline is a no-op unless `--force` is passed.
- **Two log streams, kept separate**:
  - `local/logs/meridian.jsonl` — operational (structlog)
  - `local/evidence/<DocID>.jsonl` — domain audit (append-only, one event per state transition)
- **Secrets** via `.env` only (`ANTHROPIC_API_KEY`). Never hardcoded.

## Run

```
pip install -r requirements.txt
python -m meridian pipeline              # intake + layout on all SharePoint docs
python -m meridian pipeline --doc RC-001 # single doc
python -m meridian list                  # summary of artefacts on disk
```
