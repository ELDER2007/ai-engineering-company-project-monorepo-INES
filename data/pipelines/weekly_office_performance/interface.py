"""The public face of the pipeline: the ONLY module ``services/reporting`` may import from ``data/pipelines``.

Three functions, one per endpoint (PIPELINE_DESIGN.md, section 8):

    get_latest_run(engine)                  GET  /reporting/pipeline-runs/latest
    run_weekly_office_performance(...)      POST /reporting/pipeline-runs  (runs ``weekly_office_performance_flow``)
    get_weekly_performance(engine, week)    GET  /reporting/weekly-office-program-performance

No HTTP here, and no ETL logic in ``services/``: this module only delegates to the flow and the repository.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from sqlalchemy.engine import Engine

from data.pipelines.pipeline import weekly_office_performance_flow
from data.pipelines.weekly_office_performance import repository, storage
from data.pipelines.weekly_office_performance.repository import RunInfo, WeeklyEntry, WeeklyReport

__all__ = [
    "PipelineBusyError", "PipelineRunFailed", "RunInfo", "WeeklyEntry", "WeeklyReport",
    "get_latest_run", "get_weekly_performance", "init_reporting_schema", "reporting_engine",
    "run_weekly_office_performance", "telemetry_engine",
]


class PipelineBusyError(Exception):
    """Another run of the same week is active: nothing was run."""

    def __init__(self, run: RunInfo | None = None):
        super().__init__("another run of this week is already running")
        self.run = run


class PipelineRunFailed(Exception):
    """The run started and failed; it is recorded in the execution log (``run``, when it got that far)."""

    def __init__(self, message: str, run: RunInfo | None = None):
        super().__init__(message)
        self.run = run


@lru_cache(maxsize=1)
def reporting_engine() -> Engine:
    """Connection to the ``reporting`` schema (REPORTING_DATABASE_URL, else DATABASE_URL, else the API's local SQLite)."""
    return storage.build_engine(storage.database_url("REPORTING_DATABASE_URL"))


@lru_cache(maxsize=1)
def telemetry_engine() -> Engine:
    """Read-only connection to ``telemetry_events`` (TELEMETRY_DATABASE_URL, else DATABASE_URL, else the API's local SQLite)."""
    return storage.build_engine(storage.database_url("TELEMETRY_DATABASE_URL"))


def init_reporting_schema(engine: Engine) -> None:
    storage.create_reporting_schema(engine)


def get_weekly_performance(engine: Engine, week_start: date | None = None) -> WeeklyReport | None:
    """KPIs of ``week_start`` (default: the latest computed week); ``None`` if no week was ever computed."""
    return repository.get_weekly_report(engine, week_start)


def get_latest_run(engine: Engine) -> RunInfo | None:
    """Status and metadata of the most recent run; ``None`` if the pipeline never ran."""
    return repository.get_latest_run(engine)


def run_weekly_office_performance(
    *, target_engine: Engine, source_engine: Engine, week_start: date | None = None, trigger: str = "manual"
) -> RunInfo:
    """Run the flow now and return the run it recorded. Raises ``PipelineBusyError`` if the week is already running and
    ``PipelineRunFailed`` if the run failed (after recording it). A manual run ignores the one-hour cache
    (``refresh=True``): whoever asks to recompute wants the latest events, including late ones."""
    try:
        summary = weekly_office_performance_flow(
            week_start=week_start, trigger=trigger, refresh=True, source_engine=source_engine, target_engine=target_engine
        )
    except Exception as exc:
        raise PipelineRunFailed(str(exc), repository.get_latest_run(target_engine)) from exc
    run = repository.get_run(target_engine, summary.run_id)
    if summary.state == repository.STATE_SKIPPED:
        raise PipelineBusyError(run)
    assert run is not None  # the flow always records its run
    return run
