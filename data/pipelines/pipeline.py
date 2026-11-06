"""Entry point of the weekly office/programme performance pipeline (Prefect 3).

Run it from the repository root:

    python -m data.pipelines.pipeline [--week-start YYYY-MM-DD] [--environment production] [--demo]

It turns the telemetry of one closed ISO week into the "Weekly Performance Report per Office and Programme"
(``reporting.weekly_office_program_performance``), as designed in ``PIPELINE_DESIGN.md``:

    EXTRACT    resolve_week_window -> extract_events (read-only SELECT of telemetry_events) -> save_raw_snapshot
    TRANSFORM  validate_events -> check_currency_consistency -> aggregate_by_office_programme -> reconcile
    LOAD       load_weekly_performance (ONE transaction: upsert + delete stale rows + verify)
    LOG        start_pipeline_run (Running) ... finish_pipeline_run (Completed / Failed) + save_eval_report

This file only orchestrates. The calculations are pure functions in ``data/process/weekly_performance.py``, the SQL is
in ``weekly_office_performance/repository.py``, and ``weekly_office_performance/interface.py`` is the only thing
``services/reporting`` may import.

Intermediate files: ``data/raw/`` (the events read) and ``data/eval/`` (the validation report of each run).
They are runtime output and git-ignored.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE
from prefect.runtime import flow_run
from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance import repository, storage
from data.process import weekly_performance as wp

FLOW_NAME = "weekly-office-performance"
DATA_DIR = Path(__file__).resolve().parents[1]  # <repo>/data


def _retry_delays() -> list[int]:
    """Back-off between attempts of the tasks that touch the database (PIPELINE_RETRY_DELAYS, default 5,30,120 s;
    ``PIPELINE_RETRIES=0`` turns retries off, for tests)."""
    if os.environ.get("PIPELINE_RETRIES") == "0":
        return []
    return [int(x) for x in os.environ.get("PIPELINE_RETRY_DELAYS", "5,30,120").split(",")]


_DELAYS = _retry_delays()
_RETRY = {"retries": len(_DELAYS), "retry_delay_seconds": _DELAYS or None}


def _dir(name: str) -> Path:
    base = Path(os.environ.get("PIPELINE_DATA_DIR", DATA_DIR))
    path = base / name
    path.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------------------- tasks: log


@task(cache_policy=NO_CACHE, **_RETRY)
def start_pipeline_run(target: Engine, trigger: str, week_start: date, environment: str) -> tuple[str, bool]:
    """Open the run as ``Running``. ``(run_id, False)`` means another run of this week is active: this one is ``Skipped``."""
    return repository.start_run(
        target, flow_name=FLOW_NAME, trigger=trigger, week_start=week_start, environment=environment,
        prefect_flow_run_id=str(flow_run.id) if flow_run.id else None,
    )


@task(cache_policy=NO_CACHE, **_RETRY)
def finish_pipeline_run(target: Engine, run_id: str, fields: dict[str, Any]) -> None:
    repository.finish_run(target, run_id, **fields)


# --------------------------------------------------------------------------- tasks: extract


@task(cache_policy=NO_CACHE)
def resolve_week_window(week_start: date | None) -> tuple[date, datetime, datetime]:
    return wp.resolve_week_window(week_start)


@task(cache_policy=NO_CACHE, **_RETRY)
def extract_events(source: Engine, start: datetime, end: datetime, environment: str) -> repository.Extraction:
    """Read-only. Never writes to ``telemetry_events``."""
    return repository.extract(source, start, end, environment)


@task(cache_policy=NO_CACHE)
def save_raw_snapshot(extraction: repository.Extraction, week_start: date, environment: str) -> str:
    """Keep the events this run read in ``data/raw/`` (JSON lines), so a number of the report can be traced to its events."""
    path = _dir("raw") / f"weekly_events_{week_start}_{environment}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for e in extraction.events:
            handle.write(json.dumps(
                {"event_id": e.event_id, "event_type": e.event_type, "timestamp": e.timestamp.isoformat(), "tags": dict(e.tags)},
                sort_keys=True,
            ) + "\n")
    return str(path)


# --------------------------------------------------------------------------- tasks: transform


@task(cache_policy=NO_CACHE)
def validate_events(events: list[wp.TelemetryEvent]) -> wp.ValidationResult:
    result = wp.validate_events(events)
    logger = get_run_logger()
    for reason, count in result.rejected_by_reason().items():
        logger.warning("rejected %d event(s): %s", count, reason)
    return result


@task(cache_policy=NO_CACHE)
def check_currency_consistency(events: list[wp.CleanEvent]) -> None:
    wp.check_currency_consistency(events)


@task(cache_policy=NO_CACHE)
def aggregate_by_office_programme(events: list[wp.CleanEvent], week_start: date) -> wp.Aggregation:
    return wp.aggregate_by_office_programme(events, week_start)


@task(cache_policy=NO_CACHE)
def reconcile(aggregation: wp.Aggregation, events_read: int, rejected_count: int, valid_count: int) -> dict[str, Any]:
    return wp.reconcile(aggregation, events_read=events_read, rejected_count=rejected_count, valid_count=valid_count)


# --------------------------------------------------------------------------- tasks: load


@task(cache_policy=NO_CACHE, **_RETRY)
def load_weekly_performance(target: Engine, rows: list[wp.WeeklyRow], week_start: date) -> repository.LoadResult:
    """ONE transaction: replace the week (upsert + delete stale + verify). Safe to retry: it is idempotent."""
    return repository.load_week(target, rows, week_start)


# --------------------------------------------------------------------------- evaluation output


def save_eval_report(report: dict[str, Any]) -> str | None:
    """Write the validation report of the run to ``data/eval/``. Best effort: a report that cannot be written never fails the run."""
    try:
        path = _dir("eval") / f"run_{report['week_start']}_{report['run_id'][:8]}.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
        return str(path)
    except OSError:
        return None


def _json_default(value: Any) -> Any:
    if isinstance(value, (Decimal,)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not serialisable: {type(value)}")


# --------------------------------------------------------------------------- the flow


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    state: str
    week_start: date
    error: str | None = None


@flow(name=FLOW_NAME, validate_parameters=False)
def weekly_office_performance_flow(
    week_start: date | None = None,
    trigger: str = "scheduled",
    environment: str | None = None,
    source_engine: Engine | None = None,
    target_engine: Engine | None = None,
) -> RunSummary:
    """Compute and load the weekly report for ``week_start`` (default: the last complete ISO week).

    A failure is recorded in ``reporting.pipeline_runs`` (and in the evaluation report) and then re-raised, so the
    Prefect run also ends ``Failed``. If another run of the same week is active, this one is ``Skipped``.
    """
    environment = environment or storage.default_environment()
    target = target_engine or storage.build_engine(storage.database_url("REPORTING_DATABASE_URL"))
    source = source_engine or storage.build_engine(storage.database_url("TELEMETRY_DATABASE_URL"))
    storage.create_reporting_schema(target)

    week, start, end = resolve_week_window(week_start)
    run_id, acquired = start_pipeline_run(target, trigger, week, environment)
    if not acquired:
        return RunSummary(run_id, repository.STATE_SKIPPED, week, "another run of this week is already running")

    report: dict[str, Any] = {"run_id": run_id, "week_start": week, "environment": environment, "trigger": trigger}
    fields: dict[str, Any] = {}
    raised: Exception | None = None
    try:
        extraction = extract_events(source, start, end, environment)
        report["raw_snapshot"] = save_raw_snapshot(extraction, week, environment)
        fields.update(events_read=len(extraction.events), window_events_total=extraction.window_events_total)

        checked = validate_events(extraction.events)
        fields["rejected_count"] = len(checked.rejected)
        report["rejected_by_reason"] = checked.rejected_by_reason()

        check_currency_consistency(checked.valid)
        aggregation = aggregate_by_office_programme(checked.valid, week)
        report["reconciliation"] = reconcile(aggregation, len(extraction.events), len(checked.rejected), len(checked.valid))
        report["kpis"] = [
            {"office": r.office, "programme_id": r.programme_id, "currency": r.currency,
             "total_material_cost": r.total_material_cost, "kits_delivered_count": r.kits_delivered_count,
             "shortage_events_count": r.shortage_events_count, "cost_variance_events_count": r.cost_variance_events_count}
            for r in aggregation.rows
        ]

        loaded = load_weekly_performance(target, aggregation.rows, week)
        fields.update(rows_written=loaded.written, rows_changed=loaded.changed, rows_deleted=loaded.deleted)
        fields.update(state=repository.STATE_COMPLETED, error=None)
    except Exception as exc:  # noqa: BLE001 - recorded below, then re-raised
        fields.update(state=repository.STATE_FAILED, error=f"{type(exc).__name__}: {exc}")
        raised = exc

    report.update(state=fields["state"], error=fields["error"], counts={k: v for k, v in fields.items() if k.endswith(("count", "read", "total", "written", "changed", "deleted"))})
    save_eval_report(report)
    finish_pipeline_run(target, run_id, fields)
    if raised is not None:
        raise raised
    return RunSummary(run_id, repository.STATE_COMPLETED, week)


# --------------------------------------------------------------------------- command line


def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly office/programme performance pipeline")
    parser.add_argument("--week-start", type=date.fromisoformat, default=None, help="any day of the week to compute (default: last complete week)")
    parser.add_argument("--environment", default=None, help="telemetry environment to read (default: PIPELINE_ENVIRONMENT or production)")
    parser.add_argument("--demo", action="store_true", help="run on a throw-away demo database with demo events, never on the app's data")
    args = parser.parse_args()

    source = target = None
    environment = args.environment
    if args.demo:
        from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

        source = target = storage.build_engine(storage.demo_url())
        environment = environment or storage.DEFAULT_ENVIRONMENT
        print(f"demo: {seed_telemetry(source, environment)} telemetry events loaded")
    summary = weekly_office_performance_flow(
        week_start=args.week_start, trigger="manual", environment=environment, source_engine=source, target_engine=target
    )
    print(summary)


if __name__ == "__main__":
    main()
