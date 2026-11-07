"""Routes of the reporting domain, all under ``/reporting``. HTTP only: every handler calls one function of
``data/pipelines/weekly_office_performance/interface.py`` (no SQL, no ETL here).

Same conventions as the rest of the API (inventory, suppliers): the WHOLE router needs a valid session
(``get_current_user``), so a route added later is protected by default; the route that changes numbers adds
``admin_only`` on top, like ``GET /telemetry/report`` does for its audience. Laura and Elena are not technical
administrators, so reading is for any session and triggering a run is for admins.

Handlers are plain ``def`` so FastAPI runs the blocking database work (and the Prefect flow) in its thread pool.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.engine import Engine

from auth.dependencies import admin_only, get_current_user
from data.pipelines.weekly_office_performance import interface

from .database import get_reporting_engine, get_telemetry_engine
from .schemas import PipelineRunCreate, PipelineRunOut, WeeklyReport

router = APIRouter(prefix="/reporting", tags=["reporting"], dependencies=[Depends(get_current_user)])

TargetDep = Annotated[Engine, Depends(get_reporting_engine)]
SourceDep = Annotated[Engine, Depends(get_telemetry_engine)]


@router.get(
    "/pipeline-runs/latest",
    response_model=PipelineRunOut,
    summary="Status and metadata of the latest pipeline run",
    description="The most recent run of the weekly performance pipeline: its state (`Running`, `Completed`, `Failed`, "
    "`Crashed` or `Skipped`), start and end, records processed, rows changed or deleted, warnings and the error it caught.",
    responses={404: {"description": "The pipeline has not run yet"}},
)
def latest_pipeline_run(engine: TargetDep) -> PipelineRunOut:
    run = interface.get_latest_run(engine)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The pipeline has not run yet")
    return PipelineRunOut(**asdict(run))


@router.post(
    "/pipeline-runs",
    response_model=PipelineRunOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(admin_only)],
    summary="Trigger a manual pipeline run (admins only)",
    description="Runs the weekly performance flow now, for `week_start` (any day of the week; default: the last complete "
    "ISO week), ignoring the one-hour cache so late events are picked up. Answers with the run it recorded.",
    responses={
        403: {"description": "Not an administrator"},
        409: {"description": "Another run of this week is already running"},
        500: {"description": "The run failed (it is recorded in the log as `Failed`)"},
    },
)
def trigger_pipeline_run(
    target: TargetDep, source: SourceDep, body: Annotated[PipelineRunCreate, Body()] = PipelineRunCreate()
) -> PipelineRunOut:
    try:
        run = interface.run_weekly_office_performance(target_engine=target, source_engine=source, week_start=body.week_start)
    except interface.PipelineBusyError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Another run of this week is already running") from exc
    except interface.PipelineRunFailed as exc:  # the failed run is already in the execution log
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Pipeline run failed: {exc}") from exc
    return PipelineRunOut(**asdict(run))


@router.get(
    "/weekly-office-program-performance",
    response_model=WeeklyReport,
    summary="Weekly KPIs per office and programme",
    description="One entry per office and programme of the week: material cost, kits delivered, shortage events and cost "
    "variance events, with the office's currency (EUR for valencia, USD for miami; never summed together). "
    "`week_start` is optional: by default, the latest computed week.",
    responses={404: {"description": "No week has been computed yet"}},
)
def weekly_office_program_performance(engine: TargetDep, week_start: date | None = Query(default=None)) -> WeeklyReport:
    report = interface.get_weekly_performance(engine, week_start)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No week has been computed yet")
    return WeeklyReport(week_start=report.week_start, entries=[asdict(e) for e in report.entries])
