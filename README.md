# Reconciliation Pipeline — Meridian Atlas Partners

An agentic reconciliation pipeline for a professional-services billing workflow. This repo implements the **reconciliation slice**: a deterministic, auditable floor that turns an SAP unbilled-transaction extract into a typed stream of clean passes and exception candidates, ready to be handed off to a downstream triage slice.

> **Design docs:**
> - Architecture blueprint — [`tech-architecture-flow.md`](tech-architecture-flow.md)
> - Reconciliation slice design — [`doc/design/reconciliation-flow.md`](doc/design/reconciliation-flow.md)
> - AI-agent guidance — [`CLAUDE.md`](CLAUDE.md)

---

## What this pipeline does

Three deterministic stages, wired as [LangGraph](https://github.com/langchain-ai/langgraph) nodes. No LLM in this slice — every operation is arithmetic, a table lookup, or structured-data parsing. That's the governance seam: reconciliation is the solid, auditable floor; interpretation happens in the triage slice.

| # | Stage | Agent module | Config | Output artefact |
|---|---|---|---|---|
| 1 | **SAP Ingestor** — parse the unbilled-tx CSV into typed `SAPTransaction[]`, assemble `CycleHeader`, flag data-quality issues. | `src/meridian/agents/sap_ingestor.py` | `config/agents/sap_ingestor.yaml` | `local/sap_ingested/<cycle>.json` |
| 2 | **Contract Compliance Checker** — validate every TX against the structured rules in `contract-001.md` (role rates, travel caps, subcontractor markup, expense limits, non-reimbursables, classification code). | `src/meridian/agents/contract_compliance.py` | `config/agents/contract_compliance.yaml` | `local/contract_compliance/<cycle>.json` |
| 3 | **Exception Emitter** — split every TX into `AUTO_PASS_SAP_INTERNAL` or `ExceptionCandidate` with a typed `codes[]` list. No decisions, no prioritisation. | `src/meridian/agents/exception_emitter.py` | `config/agents/exception_emitter.yaml` | `local/auto_pass/<cycle>.json`, `local/exceptions/<cycle>.json` |

Every state transition is also appended to a per-TX **evidence record** at `local/evidence/<tx_id>.jsonl` (domain audit; append-only). Operational logs are a separate stream at `local/logs/meridian.jsonl`.

---

## Tech stack

- **Python 3.11+**
- **[LangGraph](https://github.com/langchain-ai/langgraph)** ≥ 0.2 — pipeline orchestration (`StateGraph`)
- **[Pydantic v2](https://docs.pydantic.dev/)** — domain contracts at every boundary
- **[Typer](https://typer.tiangolo.com/)** — CLI (`python -m meridian ...`)
- **[structlog](https://www.structlog.org/)** — JSON operational logs
- **[PyYAML](https://pyyaml.org/)** — one config file per agent
- **[Anthropic](https://github.com/anthropics/anthropic-sdk-python)** — reserved for LLM-backed agents added in future slices (triage, document extraction); not used by the three deterministic stages here
- Filesystem for state (`local/*`); swap for object storage + SQLite later

---

## Setup

### Prerequisites

- **Python 3.11 or newer** (`python --version`)
- **Git**
- An **Anthropic API key** — only needed if you plan to run LLM-backed agents from future slices. The three stages in this slice are deterministic and run without it.

### 1. Clone

```bash
git clone https://github.com/vivek5813/reconciliation-pipeline.git
cd reconciliation-pipeline
```

### 2. Create a virtual environment

**macOS / Linux**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
pip install -e .
```

The editable install (`-e .`) registers the `meridian` console entry point and the `src/meridian/` package.

### 4. Configure secrets

```bash
cp .env.example .env         # Windows: copy .env.example .env
```

Edit `.env` and fill in `ANTHROPIC_API_KEY` if you'll be running LLM-backed agents. `.env` is `.gitignore`d — never commit it.

### 5. Verify

```bash
python -m meridian --help
```

You should see the Typer help for `ingest`, `check`, `emit`, `pipeline`, `list`, and `show`.

---

## Running the pipeline

The default cycle (`2026-04`) and all paths are set in [`config/pipeline.yaml`](config/pipeline.yaml). Sample inputs live under [`doc/appendix-sample-data/`](doc/appendix-sample-data/).

### Full end-to-end run

```bash
python -m meridian pipeline
```

Runs all three stages in order: ingest → contract compliance → exception emit. Idempotent — re-running is a no-op unless `--force` is passed.

### Per-stage runs

```bash
python -m meridian ingest           # Stage 1: SAP Ingestor
python -m meridian check            # Stage 2: Contract Compliance Checker
python -m meridian emit             # Stage 3: Exception Emitter
```

Each stage reads the cached artefact of the previous stage from `local/` and writes its own.

### Force recomputation

```bash
python -m meridian pipeline --force
python -m meridian ingest --force
```

### Inspect artefacts on disk

```bash
python -m meridian list             # Summary of all artefacts for the current cycle
python -m meridian show TX-2026-04-0044    # Full evidence trail for one TX
```

---

## Project layout

```
config/
  pipeline.yaml                      # cycle, paths, log level/file
  agents/
    sap_ingestor.yaml                # one YAML per agent — model, prompts, thresholds live here
    contract_compliance.yaml
    exception_emitter.yaml

src/meridian/
  cli.py            # Typer CLI (ingest / check / emit / pipeline / list / show)
  config.py         # Pydantic config loaders for pipeline.yaml and agent YAMLs
  contracts.py      # Pydantic domain contracts (SAPTransaction, CycleHeader, ExceptionCandidate, ...)
  evidence.py       # Append-only per-TX evidence JSONL
  graph.py          # LangGraph wiring — one StateGraph for the slice
  log.py            # structlog setup
  agents/
    sap_ingestor.py         # deterministic
    contract_compliance.py  # deterministic
    exception_emitter.py    # deterministic

doc/
  design/
    reconciliation-flow.md           # the design doc for this slice
  appendix-sample-data/              # SharePoint-style drop folder with sample inputs
    contracts/contract-001.md
    transactions/unbilled-2026-04.csv
    sap-outputs/
    documents/
    ...
  participant-brief.md               # hackathon brief

tech-architecture-flow.md            # the architecture blueprint — read this before changing anything
CLAUDE.md                            # AI-agent guidance (short)
.env.example                         # copy to .env; .env is gitignored
local/                               # all runtime output; gitignored
```

---

## Conventions (the non-negotiables)

Pulled from [`tech-architecture-flow.md`](tech-architecture-flow.md) and `.cursor/rules/consult-architecture-blueprint.mdc`:

- **One job per stage**, deterministic by default. LLMs only where human judgment is required.
- **One YAML config per agent** under `config/agents/`. `model:`, `prompt_version:`, and thresholds live there — never in code. Swap models by editing YAML.
- **Each agent is a LangGraph node** exposing `node(state) -> state`. Add new agents in `src/meridian/agents/` and wire them in `graph.py`.
- **Pydantic contracts at every boundary** (YAML → config, LLM JSON → DTO, state → `PipelineState`). No raw dicts crossing seams.
- **Idempotent re-runs** — no-op unless `--force` is passed.
- **Confidence is a first-class output** — a separate router node decides HITL vs. auto-pass; agents never self-escalate.
- **Two separate log streams**, never conflated:
  - `local/logs/meridian.jsonl` — operational, structlog JSON
  - `local/evidence/<unit_id>.jsonl` — domain audit, append-only, one event per state transition
- **HITL decides, doesn't invent** — each analyst action emits one `DecisionEvent`.
- **Seams, not silos** — a stage's output contract is the next stage's input contract.
- **Secrets via `.env` only**. Never hardcoded.

If a change contradicts the blueprint, call it out explicitly before writing code.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python -m meridian: No module named meridian` | You skipped `pip install -e .`. Run it from the repo root with your venv activated. |
| `ingest_source_missing` error | The CSV path in `config/agents/sap_ingestor.yaml` doesn't exist relative to `paths.data_dir` in `config/pipeline.yaml`. |
| `check_sap_ingest_missing` / `emit_upstream_missing` | A previous stage hasn't run yet. Either run that stage, or just run `python -m meridian pipeline`. |
| Stage returns cached results when you want fresh ones | Pass `--force`. |
| ANTHROPIC_API_KEY errors | The three stages in this slice are deterministic and don't need it; LLM agents from future slices do. Fill `.env`. |

---

## License

Internal / hackathon project. No license granted.
