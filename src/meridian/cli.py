"""Typer CLI — one command per stage plus a `pipeline` command plus `list`.

Blueprint §14: every command follows the same five-section skeleton
  1. Load .env + config.
  2. Configure structlog.
  3. Load prior-stage artefacts from disk, validate with Pydantic contracts.
  4. Loop over units, calling the stage helper.
  5. Write a `<stage>_start` / `<stage>_done` operational log pair with counts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from .agents.contract_compliance import do_check
from .agents.exception_emitter import do_emit
from .agents.sap_ingestor import do_ingest
from .config import (
    ContractComplianceConfig,
    ExceptionEmitterConfig,
    SapIngestorConfig,
    load_agent_config,
    load_pipeline_config,
)
from .contracts import (
    AutoPassBucket,
    ContractComplianceReport,
    ExceptionBucket,
    SapIngestResult,
)
from .graph import run_pipeline
from .log import configure_logging, get_logger


app = typer.Typer(
    add_completion=False,
    help="Meridian Atlas Partners — reconciliation pipeline CLI.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Shared setup
# ---------------------------------------------------------------------------


def _bootstrap():
    """Load .env, pipeline config, and configure logging. Return the config."""
    load_dotenv()
    cfg = load_pipeline_config()
    configure_logging(cfg.log_file, level=cfg.logging.level)
    return cfg


# ---------------------------------------------------------------------------
# `ingest` — run the SAP Ingestor stage only
# ---------------------------------------------------------------------------


@app.command()
def ingest(
    source: Optional[Path] = typer.Option(
        None,
        "--source",
        help="Override the SAP source CSV path. Defaults to the configured one.",
    ),
    force: bool = typer.Option(
        False, "--force", help="Ignore cached artefact and recompute."
    ),
) -> None:
    """Run the SAP Ingestor on the configured source CSV."""
    cfg = _bootstrap()
    agent_cfg = load_agent_config("sap_ingestor", SapIngestorConfig)
    log = get_logger("cli", command="ingest")

    log.info(
        "ingest_start",
        cycle=cfg.cycle,
        source=str(source or (cfg.data_dir / agent_cfg.source.filename)),
        force=force,
    )

    try:
        result, fresh = do_ingest(
            csv_path=source,
            force=force,
            pipeline_cfg=cfg,
            agent_cfg=agent_cfg,
        )
    except FileNotFoundError as exc:
        log.error("ingest_source_missing", error=str(exc))
        raise typer.Exit(code=2)

    log.info(
        "ingest_done",
        cycle=cfg.cycle,
        fresh=fresh,
        tx_count=result.cycle_header.tx_count,
        held=result.cycle_header.held_item_count,
        anomalies=len(result.anomalies),
        errors=len(result.ingest_errors),
    )

    # Human-visible summary.
    typer.echo("")
    typer.echo(f"SAP Ingest {'(fresh)' if fresh else '(cached)'} — cycle {cfg.cycle}")
    typer.echo(f"  project_id       : {result.cycle_header.project_id}")
    typer.echo(f"  transactions     : {result.cycle_header.tx_count}")
    typer.echo(f"  labour hours     : {result.cycle_header.total_labour_hours}")
    typer.echo(f"  held items       : {result.cycle_header.held_item_count}")
    typer.echo(f"  anomalies        : {len(result.anomalies)}")
    typer.echo(f"  ingest errors    : {len(result.ingest_errors)}")


# ---------------------------------------------------------------------------
# `check` — run the Contract Compliance Checker stage only
# ---------------------------------------------------------------------------


@app.command()
def check(
    force: bool = typer.Option(
        False, "--force", help="Ignore cached artefact and recompute."
    ),
) -> None:
    """Run the Contract Compliance Checker over the cached SAP-ingest artefact."""
    cfg = _bootstrap()
    agent_cfg = load_agent_config("contract_compliance", ContractComplianceConfig)
    log = get_logger("cli", command="check")

    log.info(
        "check_start",
        cycle=cfg.cycle,
        rules_version=agent_cfg.rules.rules_version,
        force=force,
    )

    try:
        report, fresh = do_check(
            force=force,
            pipeline_cfg=cfg,
            agent_cfg=agent_cfg,
        )
    except FileNotFoundError as exc:
        log.error("check_sap_ingest_missing", error=str(exc))
        raise typer.Exit(code=2)

    s = report.summary
    log.info(
        "check_done",
        cycle=cfg.cycle,
        fresh=fresh,
        rules_version=report.contract_rules_version,
        tx_checked=s.total_txs_checked,
        pass_count=s.pass_count,
        hard=s.violations.get("hard", 0),
        soft=s.violations.get("soft", 0),
        info=s.violations.get("info", 0),
        cycle_level_violations=len(report.cycle_level_violations),
        codes_present=s.violation_codes_present,
    )

    typer.echo("")
    typer.echo(
        f"Contract Compliance {'(fresh)' if fresh else '(cached)'} — cycle {cfg.cycle}"
    )
    typer.echo(f"  rules_version    : {report.contract_rules_version}")
    typer.echo(f"  tx checked       : {s.total_txs_checked}")
    typer.echo(f"  pass             : {s.pass_count}")
    typer.echo(
        f"  violations       : hard={s.violations.get('hard', 0)} "
        f"soft={s.violations.get('soft', 0)} info={s.violations.get('info', 0)}"
    )
    if report.cycle_level_violations:
        typer.echo(f"  cycle-level      : {len(report.cycle_level_violations)}")
        for v in report.cycle_level_violations:
            typer.echo(f"    [{v.severity:4}] {v.code}: {v.detail}")
    if s.violation_codes_present:
        typer.echo(f"  codes present    : {', '.join(s.violation_codes_present)}")


# ---------------------------------------------------------------------------
# `emit` — run the Exception Emitter stage only
# ---------------------------------------------------------------------------


@app.command()
def emit(
    force: bool = typer.Option(
        False, "--force", help="Ignore cached artefacts and recompute."
    ),
) -> None:
    """Run the Exception Emitter over cached SAP-ingest + contract-compliance artefacts."""
    cfg = _bootstrap()
    agent_cfg = load_agent_config("exception_emitter", ExceptionEmitterConfig)
    log = get_logger("cli", command="emit")

    log.info(
        "emit_start",
        cycle=cfg.cycle,
        emitter_logic_version=agent_cfg.emitter_logic_version,
        force=force,
    )

    try:
        auto_pass_bucket, exception_bucket, fresh = do_emit(
            force=force,
            pipeline_cfg=cfg,
            agent_cfg=agent_cfg,
        )
    except FileNotFoundError as exc:
        log.error("emit_upstream_missing", error=str(exc))
        raise typer.Exit(code=2)

    s = auto_pass_bucket.summary
    log.info(
        "emit_done",
        cycle=cfg.cycle,
        fresh=fresh,
        total_txs=s.total_txs,
        auto_pass=s.auto_pass_count,
        exceptions=s.exception_count,
        codes_present=s.codes_present,
    )

    typer.echo("")
    typer.echo(
        f"Exception Emitter {'(fresh)' if fresh else '(cached)'} — cycle {cfg.cycle}"
    )
    typer.echo(f"  total txs        : {s.total_txs}")
    typer.echo(
        f"  buckets          : auto_pass={s.auto_pass_count} "
        f"exceptions={s.exception_count}"
    )
    if s.codes_by_count:
        typer.echo("  codes by count   :")
        for code, count in sorted(
            s.codes_by_count.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            typer.echo(f"    {count:4d}  {code}")
    cc = exception_bucket.cycle_context
    if cc.cycle_level_violations:
        typer.echo(
            f"  cycle-level viols: {len(cc.cycle_level_violations)} "
            f"(carried on exception bucket)"
        )
    if cc.cycle_anomalies:
        typer.echo(
            f"  cycle anomalies  : {len(cc.cycle_anomalies)} "
            f"(carried on exception bucket)"
        )


# ---------------------------------------------------------------------------
# `pipeline` — chain all stages (ingest + contract compliance + exception emit)
# ---------------------------------------------------------------------------


@app.command()
def pipeline(
    force: bool = typer.Option(False, "--force", help="Ignore cached artefacts."),
) -> None:
    """Run the full pipeline end-to-end (ingest + contract compliance + exception emit)."""
    cfg = _bootstrap()
    log = get_logger("cli", command="pipeline")

    log.info("pipeline_start", cycle=cfg.cycle, force=force)
    final = run_pipeline(force=force)

    if final.sap_ingest is None:
        log.error("pipeline_failed_no_ingest_result")
        raise typer.Exit(code=1)
    if final.contract_compliance is None:
        log.error(
            "pipeline_failed_no_contract_compliance",
            errors=final.errors,
        )
        raise typer.Exit(code=1)
    if final.auto_pass is None or final.exceptions is None:
        log.error(
            "pipeline_failed_no_exception_buckets",
            errors=final.errors,
        )
        raise typer.Exit(code=1)

    header = final.sap_ingest.cycle_header
    s = final.contract_compliance.summary
    emit_summary = final.auto_pass.summary
    log.info(
        "pipeline_done",
        cycle=cfg.cycle,
        tx_count=header.tx_count,
        ingest_fresh=final.sap_ingest_fresh,
        check_fresh=final.contract_compliance_fresh,
        emit_fresh=final.exception_emitter_fresh,
        pass_count=s.pass_count,
        violations_hard=s.violations.get("hard", 0),
        violations_soft=s.violations.get("soft", 0),
        violations_info=s.violations.get("info", 0),
        auto_pass=emit_summary.auto_pass_count,
        exceptions=emit_summary.exception_count,
    )

    typer.echo("")
    typer.echo(
        f"Pipeline done — cycle {cfg.cycle}, "
        f"{header.tx_count} TXs ({header.held_item_count} held)."
    )
    typer.echo(
        f"  compliance: pass={s.pass_count} "
        f"hard={s.violations.get('hard', 0)} "
        f"soft={s.violations.get('soft', 0)} "
        f"info={s.violations.get('info', 0)}"
    )
    if s.violation_codes_present:
        typer.echo(f"  codes     : {', '.join(s.violation_codes_present)}")
    typer.echo(
        f"  buckets   : auto_pass={emit_summary.auto_pass_count} "
        f"exceptions={emit_summary.exception_count}"
    )
    if emit_summary.codes_by_count:
        top = sorted(
            emit_summary.codes_by_count.items(), key=lambda kv: (-kv[1], kv[0])
        )[:5]
        pretty = ", ".join(f"{code}:{count}" for code, count in top)
        typer.echo(f"  top codes : {pretty}")


# ---------------------------------------------------------------------------
# `list` — summarise cached artefacts
# ---------------------------------------------------------------------------


@app.command("list")
def list_artefacts() -> None:
    """Summarise the artefacts currently on disk for the configured cycle."""
    cfg = _bootstrap()
    log = get_logger("cli", command="list")

    artefact = cfg.sap_ingested_dir / f"{cfg.cycle}.json"
    if not artefact.exists():
        typer.echo(f"No SAP ingest artefact for cycle {cfg.cycle} at {artefact}.")
        typer.echo("Run `python -m meridian ingest` first.")
        raise typer.Exit(code=0)

    result = SapIngestResult.model_validate_json(artefact.read_text("utf-8"))
    header = result.cycle_header

    typer.echo(f"Cycle           : {header.cycle}")
    typer.echo(f"Project         : {header.project_id}")
    typer.echo(f"Source          : {header.source_filename}")
    typer.echo(f"Source hash     : {header.source_hash[:16]}\u2026")
    typer.echo(f"Ingested at     : {result.ingested_at.isoformat()}")
    typer.echo(f"Transactions    : {header.tx_count} "
               f"(labour {header.labour_tx_count}, expense {header.expense_tx_count})")
    typer.echo(f"Labour hours    : {header.total_labour_hours}")
    typer.echo(f"Held items      : {header.held_item_count} "
               f"({header.held_item_hours} hrs)")
    if header.flags:
        typer.echo(f"Flags           : {', '.join(header.flags)}")

    if result.anomalies:
        typer.echo("")
        typer.echo("Anomalies:")
        for a in result.anomalies:
            tail = f" ({len(a.affected_tx_ids)} tx)" if a.affected_tx_ids else ""
            typer.echo(f"  [{a.severity:7}] {a.code}: {a.message}{tail}")

    if result.ingest_errors:
        typer.echo("")
        typer.echo("Ingest errors:")
        for err in result.ingest_errors:
            typer.echo(f"  row {err.row_number}: {err.code} \u2014 {err.message}")

    # ---- Contract-compliance summary (if the stage has run) --------------
    cc_path = cfg.contract_compliance_dir / f"{cfg.cycle}.json"
    if cc_path.exists():
        report = ContractComplianceReport.model_validate_json(
            cc_path.read_text("utf-8")
        )
        s = report.summary
        typer.echo("")
        typer.echo("Contract compliance:")
        typer.echo(f"  rules_version    : {report.contract_rules_version}")
        typer.echo(f"  checked_at       : {report.checked_at.isoformat()}")
        typer.echo(
            f"  tx checked / pass: {s.total_txs_checked} / {s.pass_count}"
        )
        typer.echo(
            f"  violations       : hard={s.violations.get('hard', 0)} "
            f"soft={s.violations.get('soft', 0)} info={s.violations.get('info', 0)}"
        )
        if s.violation_codes_present:
            typer.echo(f"  codes present    : {', '.join(s.violation_codes_present)}")
        if report.cycle_level_violations:
            typer.echo("  cycle-level:")
            for v in report.cycle_level_violations:
                typer.echo(f"    [{v.severity:4}] {v.code}: {v.detail}")

        # Per-TX violation lines (only non-PASS blocks).
        failed = [b for b in report.per_tx if b.status == "VIOLATION"]
        if failed:
            typer.echo("")
            typer.echo("Per-TX violations:")
            for b in failed:
                for v in b.violations:
                    typer.echo(
                        f"  {b.tx_id}  [{v.severity:4}] {v.code}: {v.detail}"
                    )
    else:
        typer.echo("")
        typer.echo(
            "Contract compliance: not run for this cycle. "
            "Run `python -m meridian check`."
        )

    # ---- Exception emitter buckets (if the stage has run) ----------------
    ap_path = cfg.auto_pass_dir / f"{cfg.cycle}.json"
    ex_path = cfg.exceptions_dir / f"{cfg.cycle}.json"
    if ap_path.exists() and ex_path.exists():
        ap_bucket = AutoPassBucket.model_validate_json(ap_path.read_text("utf-8"))
        ex_bucket = ExceptionBucket.model_validate_json(ex_path.read_text("utf-8"))
        s = ap_bucket.summary

        typer.echo("")
        typer.echo("Exception emitter:")
        typer.echo(f"  emitted_at       : {ap_bucket.emitted_at.isoformat()}")
        typer.echo(f"  total txs        : {s.total_txs}")
        typer.echo(
            f"  buckets          : auto_pass={s.auto_pass_count} "
            f"exceptions={s.exception_count}"
        )
        if s.codes_by_count:
            top = sorted(
                s.codes_by_count.items(), key=lambda kv: (-kv[1], kv[0])
            )[:5]
            typer.echo("  top codes        :")
            for code, count in top:
                typer.echo(f"    {count:4d}  {code}")

        # Top-5 candidate ids by code count — a quick signal of the loudest TXs.
        if ex_bucket.candidates:
            noisiest = sorted(
                ex_bucket.candidates, key=lambda c: (-len(c.codes), c.tx_id)
            )[:5]
            typer.echo("  noisiest cands   :")
            for c in noisiest:
                typer.echo(
                    f"    {c.candidate_id}  {c.tx_id}  "
                    f"[{len(c.codes)}] {', '.join(c.codes)}"
                )
    else:
        typer.echo("")
        typer.echo(
            "Exception emitter: not run for this cycle. "
            "Run `python -m meridian emit`."
        )

    log.info("list_shown", cycle=cfg.cycle, artefact=str(artefact))


# ---------------------------------------------------------------------------
# `show` — dump a single transaction's evidence trail (handy for debugging)
# ---------------------------------------------------------------------------


@app.command("show")
def show_tx(tx_id: str = typer.Argument(..., help="Transaction / timecard id.")) -> None:
    """Print the evidence JSONL for one TX."""
    cfg = _bootstrap()
    path = cfg.evidence_dir / f"{tx_id}.jsonl"
    if not path.exists():
        typer.echo(f"No evidence file for {tx_id} at {path}.")
        raise typer.Exit(code=1)
    for line in path.read_text("utf-8").splitlines():
        try:
            event = json.loads(line)
            typer.echo(json.dumps(event, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            typer.echo(line)


if __name__ == "__main__":  # pragma: no cover
    app()
