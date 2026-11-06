"""Entry point of the weekly office/programme performance pipeline (Prefect 3).

Run it as a script, from anywhere:

    python data/pipelines/pipeline.py [--week-start YYYY-MM-DD] [--environment production] [--refresh] [--demo]
    python -m data.pipelines.pipeline  ...            (same thing, from the repository root)

Exit code: 0 = completed (or skipped because the week is already running), 1 = failed (the failure is in the
execution log), so a scheduler can tell.

It turns the telemetry of one closed ISO week into the "Weekly Performance Report per Office and Programme"
(``reporting.weekly_office_program_performance``), as designed in ``PIPELINE_DESIGN.md``:

    EXTRACT    resolve_week_window -> extract_events -> (count_window_events, save_raw_snapshot)
    TRANSFORM  validate_events -> check_currency_consistency -> aggregate_by_office_programme -> reconcile
    LOAD       load_weekly_performance   (ONE transaction: upsert + delete stale rows + verify)
    LOG        start_pipeline_run ... (save_eval_report) ... finish_pipeline_run

Resilience (the four requirements of the ticket):

* PARTIAL FAILURES. Tasks are CRITICAL (their failure stops the run: there is no honest report without them) or
  OPTIONAL (``count_window_events``, ``save_raw_snapshot``, ``save_eval_report``: a failure is logged in the run's
  ``warnings`` and the flow continues). Whatever happens, the run is closed in the execution log.
* RETRIES. Every task that touches the database (``extract_events``, ``load_weekly_performance``, the run log and the
  optional count) retries with a back-off (5 s, 30 s, 2 min) to absorb transient failures.
* CACHE. A task that completed less than an hour ago is not run again: ``extract_events`` (the expensive read) and
  ``aggregate_by_office_programme`` reuse their result for one hour, so rerunning after a failed load does not read the
  source again. The load, the log and the checks are NEVER cached: they must act every time. ``refresh=True`` (the
  manual trigger and ``--refresh``) bypasses the cache, to pick up late events.
* SCRIPT. ``main()`` below.

This file only orchestrates. The calculations are pure functions in ``data/process/weekly_performance.py``, the SQL is
in ``weekly_office_performance/repository.py``, and ``weekly_office_performance/interface.py`` is the only thing
``services/reporting`` may import. Intermediate files: ``data/raw/`` (the events read) and ``data/eval/`` (the
validation report of each run); they are runtime output and git-ignored.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:  # `python data/pipelines/pipeline.py`: make `data.` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from prefect import flow, get_run_logger, task
from prefect.cache_policies import INPUTS, NO_CACHE
from prefect.runtime import flow_run
from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance import repository, storage
from data.process import weekly_performance as wp

FLOW_NAME = "weekly-office-performance"
DATA_DIR = Path(__file__).resolve().parents[1]  # <repo>/data
CACHE_TTL = timedelta(hours=1)  # a task that completed within this window is not run again


def _retry_delays() -> list[int]:
    """Back-off between attempts (PIPELINE_RETRY_DELAYS, default 5,30,120 s). ``PIPELINE_RETRIES=0`` turns retries off."""
    if os.environ.get("PIPELINE_RETRIES") == "0":
        return []
    return [int(x) for x in os.environ.get("PIPELINE_RETRY_DELAYS", "5,30,120").split(",")]


_DELAYS = _retry_delays()
RETRY = {"retries": len(_DELAYS), "retry_delay_seconds": _DELAYS or None}  # tasks that touch the database
RETRY_LIGHT = {"retries": min(1, len(_DELAYS)), "retry_delay_seconds": _DELAYS[0] if _DELAYS else None}  # optional ones: fail fast


def _dir(name: str) -> Path:
    path = Path(os.environ.get("PIPELINE_DATA_DIR", DATA_DIR)) / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_cache_key(_context: Any, parameters: dict[str, Any]) -> str:
    """Same database, environment and window = same extraction. The engine is not hashable, so its URL (password hidden) is the key."""
    source: Engine = parameters["source"]
    return "|".join(
        ["extract", source.url.render_as_string(hide_password=True), parameters["environment"],
         parameters["start"].isoformat(), parameters["end"].isoformat()]
    )


# --------------------------------------------------------------------------- critical tasks: the run log


@task(cache_policy=NO_CACHE, **RETRY)
def start_pipeline_run(target: Engine, trigger: str, week_start: date, environment: str) -> tuple[str, bool]:
    """Open the run as ``Running``. ``(run_id, False)`` means another run of this week is active: this one is ``Skipped``."""
    return repository.start_run(
        target, flow_name=FLOW_NAME, trigger=trigger, week_start=week_start, environment=environment,
        prefect_flow_run_id=str(flow_run.id) if flow_run.id else None,
    )


@task(cache_policy=NO_CACHE, **RETRY)
def finish_pipeline_run(target: Engine, run_id: str, fields: dict[str, Any]) -> None:
    repository.finish_run(target, run_id, **fields)


# --------------------------------------------------------------------------- critical tasks: extract


@task(cache_policy=NO_CACHE)
def resolve_week_window(week_start: date | None) -> tuple[date, datetime, datetime]:
    return wp.resolve_week_window(week_start)


@task(cache_key_fn=_extract_cache_key, cache_expiration=CACHE_TTL, persist_result=True, **RETRY)
def extract_events(source: Engine, start: datetime, end: datetime, environment: str) -> list[wp.TelemetryEvent]:
    """The expensive read, cached for an hour. Read-only: never writes to ``telemetry_events``."""
    return repository.extract(source, start, end, environment)


# --------------------------------------------------------------------------- optional tasks (a failure is a warning)


@task(cache_policy=NO_CACHE, **RETRY_LIGHT)
def count_window_events(source: Engine, start: datetime, end: datetime, environment: str) -> int:
    """OPTIONAL. Liveness signal (events of any type in the window). If it fails the report is still correct; the count stays unknown."""
    return repository.count_window_events(source, start, end, environment)


@task(cache_policy=NO_CACHE)
def save_raw_snapshot(events: list[wp.TelemetryEvent], week_start: date, environment: str) -> str:
    """OPTIONAL. Keep the events this run read in ``data/raw/`` (JSON lines), to trace a number of the report to its events."""
    path = _dir("raw") / f"weekly_events_{week_start}_{environment}.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for e in events:
            handle.write(json.dumps(
                {"event_id": e.event_id, "event_type": e.event_type, "timestamp": e.timestamp.isoformat(), "tags": dict(e.tags)},
                sort_keys=True,
            ) + "\n")
    return str(path)


@task(cache_policy=NO_CACHE)
def save_eval_report(report: dict[str, Any]) -> str:
    """OPTIONAL. Write the validation report of the run to ``data/eval/``."""
    path = _dir("eval") / f"run_{report['week_start']}_{report['run_id'][:8]}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True, default=_json_default), encoding="utf-8")
    return str(path)


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"not serialisable: {type(value)}")


def optional(run_task: Callable[..., Any], *args: Any, label: str, warnings: list[str], default: Any = None) -> Any:
    """Run an OPTIONAL task: if it fails, record a warning and return ``default`` so the flow goes on.

    ``return_state=True`` makes Prefect hand back the task's state instead of raising its error."""
    state = run_task(*args, return_state=True)
    if state.is_completed():
        return state.result()
    error = state.result(raise_on_failure=False)
    warnings.append(f"{label}: {type(error).__name__}: {error}")
    get_run_logger().warning("optional task %s failed, continuing: %s", label, error)
    return default


# --------------------------------------------------------------------------- critical tasks: transform and load


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


@task(cache_policy=INPUTS, cache_expiration=CACHE_TTL, persist_result=True)
def aggregate_by_office_programme(events: list[wp.CleanEvent], week_start: date) -> wp.Aggregation:
    """The transformation, cached for an hour by its inputs: same events and week give the same rows, so reuse is safe."""
    return wp.aggregate_by_office_programme(events, week_start)


@task(cache_policy=NO_CACHE)
def reconcile(aggregation: wp.Aggregation, events_read: int, rejected_count: int, valid_count: int) -> dict[str, Any]:
    return wp.reconcile(aggregation, events_read=events_read, rejected_count=rejected_count, valid_count=valid_count)


@task(cache_policy=NO_CACHE, **RETRY)
def load_weekly_performance(target: Engine, rows: list[wp.WeeklyRow], week_start: date) -> repository.LoadResult:
    """ONE transaction: replace the week (upsert + delete stale + verify). Never cached; safe to retry: it is idempotent."""
    return repository.load_week(target, rows, week_start)


# --------------------------------------------------------------------------- the flow


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    state: str
    week_start: date
    error: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


@flow(name=FLOW_NAME, validate_parameters=False)
def weekly_office_performance_flow(
    week_start: date | None = None,
    trigger: str = "scheduled",
    environment: str | None = None,
    refresh: bool = False,
    source_engine: Engine | None = None,
    target_engine: Engine | None = None,
) -> RunSummary:
    """Compute and load the weekly report for ``week_start`` (default: the last complete ISO week).

    ``refresh=True`` ignores the one-hour cache (to see late events). A critical failure is recorded in
    ``reporting.pipeline_runs`` and then re-raised, so the Prefect run also ends ``Failed``. A failure of an optional
    task is recorded as a warning and the run completes. If another run of the same week is active, this one is ``Skipped``.
    """
    environment = environment or storage.default_environment()
    target = target_engine or storage.build_engine(storage.database_url("REPORTING_DATABASE_URL"))
    source = source_engine or storage.build_engine(storage.database_url("TELEMETRY_DATABASE_URL"))
    storage.create_reporting_schema(target)

    extract = extract_events.with_options(refresh_cache=True) if refresh else extract_events
    aggregate = aggregate_by_office_programme.with_options(refresh_cache=True) if refresh else aggregate_by_office_programme

    week, start, end = resolve_week_window(week_start)
    run_id, acquired = start_pipeline_run(target, trigger, week, environment)
    if not acquired:
        return RunSummary(run_id, repository.STATE_SKIPPED, week, "another run of this week is already running")

    warnings: list[str] = []
    report: dict[str, Any] = {"run_id": run_id, "week_start": week, "environment": environment, "trigger": trigger}
    fields: dict[str, Any] = {}
    raised: Exception | None = None
    try:
        events = extract(source, start, end, environment)  # critical
        fields["events_read"] = len(events)
        fields["window_events_total"] = optional(count_window_events, source, start, end, environment, label="count_window_events", warnings=warnings)
        report["raw_snapshot"] = optional(save_raw_snapshot, events, week, environment, label="save_raw_snapshot", warnings=warnings)

        checked = validate_events(events)  # critical from here to the load
        fields["rejected_count"] = len(checked.rejected)
        report["rejected_by_reason"] = checked.rejected_by_reason()

        check_currency_consistency(checked.valid)
        aggregation = aggregate(checked.valid, week)
        report["reconciliation"] = reconcile(aggregation, len(events), len(checked.rejected), len(checked.valid))
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

    report.update(state=fields["state"], error=fields["error"], warnings=list(warnings),
                  counts={k: v for k, v in fields.items() if k not in ("state", "error")})
    optional(save_eval_report, report, label="save_eval_report", warnings=warnings)
    fields["warnings"] = "; ".join(warnings) or None
    finish_pipeline_run(target, run_id, fields)
    if raised is not None:
        raise raised
    return RunSummary(run_id, repository.STATE_COMPLETED, week, warnings=tuple(warnings))


# --------------------------------------------------------------------------- command line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Weekly office/programme performance pipeline")
    parser.add_argument("--week-start", type=date.fromisoformat, default=None, help="any day of the week to compute (default: last complete week)")
    parser.add_argument("--environment", default=None, help="telemetry environment to read (default: PIPELINE_ENVIRONMENT or production)")
    parser.add_argument("--refresh", action="store_true", help="ignore the one-hour cache and read the source again (to pick up late events)")
    parser.add_argument("--trigger", choices=("scheduled", "manual"), default="manual", help="how this run is labelled in the log (default: manual)")
    parser.add_argument("--demo", action="store_true", help="run on a throw-away demo database with demo events, never on the app's data")
    args = parser.parse_args(argv)

    source = target = None
    environment = args.environment
    if args.demo:
        from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

        source = target = storage.build_engine(storage.demo_url())
        environment = environment or storage.DEFAULT_ENVIRONMENT
        print(f"demo: {seed_telemetry(source, environment)} telemetry events loaded")
    try:
        summary = weekly_office_performance_flow(
            week_start=args.week_start, trigger=args.trigger, environment=environment, refresh=args.refresh,
            source_engine=source, target_engine=target,
        )
    except Exception as exc:  # noqa: BLE001 - already recorded in the execution log by the flow
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
