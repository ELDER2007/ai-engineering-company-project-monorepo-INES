"""The tasks. Today: the weekly business-performance pipeline, the one slow operation of the API.

Why this one: it is the only endpoint that takes seconds. ``POST /reporting/pipeline-runs`` waited 7 to 35 s for the pipeline to finish; every
other endpoint answers in under 0.3 s (measured, see ``README.md``). It runs Prefect, reads the telemetry and rewrites the weekly KPIs: exactly
the kind of work that belongs in a worker.

The message carries ONE parameter, ``week_start`` (a date as text, or null for the last complete week): the data is read from the database by
the worker, it never travels through Redis.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import date

from celery.signals import worker_init

from data.pipelines.weekly_office_performance import interface
from reporting.schemas import PipelineRunOut
from services.celery_app import app

from .base import MAX_RETRIES, ObservedTask, run_with_retries

logger = logging.getLogger("async_tasks")

RUN_WEEKLY_PIPELINE = "async_tasks.run_weekly_pipeline"
_schema_ready = False


def ensure_reporting_schema() -> None:
    """Create the ``reporting`` tables if they are missing, once per process. Idempotent and cheap after the first time."""
    global _schema_ready
    if not _schema_ready:
        interface.init_reporting_schema(interface.reporting_engine())
        _schema_ready = True


@worker_init.connect
def _prepare_schema(**_: object) -> None:
    """In the MAIN process of the worker, before it forks the processes that run tasks: two of them creating the tables at the same instant on a
    new database collide (``table pipeline_runs already exists``). The children inherit the result. If the database is not reachable now,
    the first task asks again (and is retried like any other failure)."""
    try:
        ensure_reporting_schema()
    except Exception as problem:  # noqa: BLE001
        logger.warning("worker start: the reporting schema could not be prepared yet (%s: it will be tried again by the first task)", type(problem).__name__)


@app.task(bind=True, base=ObservedTask, name=RUN_WEEKLY_PIPELINE, max_retries=MAX_RETRIES)
def run_weekly_pipeline(self, week_start: str | None = None) -> dict:
    """Run the weekly performance pipeline for the ISO week of ``week_start`` (default: the last complete week) and return the run it recorded.

    What is retried: any failure that can pass (the database is not reachable, the ephemeral Prefect server did not answer in time).
    What is not: a wrong argument (``ValueError``), which fails the same way every time.
    What is not a failure either: another run of the SAME week is already in progress. The pipeline refuses to run a week twice at once, and a
    duplicate request is harmless, so the task ends ``success`` with ``{"state": "Skipped", ...}`` (like the nightly job's ``skipped``) instead of
    being retried (a run lasts longer than the waits) and ending in the dead-letter queue as if something had broken.
    """
    def work() -> dict:
        week = date.fromisoformat(week_start) if week_start else None  # ValueError: not retried
        ensure_reporting_schema()
        try:
            run = interface.run_weekly_office_performance(
                target_engine=interface.reporting_engine(), source_engine=interface.telemetry_engine(), week_start=week
            )
        except interface.PipelineBusyError:
            return {"state": "Skipped", "week_start": week_start, "detail": "another run of this week is already running"}
        return PipelineRunOut(**asdict(run)).model_dump(mode="json")

    return run_with_retries(self, work)  # the growing wait, or the dead-letter queue after the last attempt
