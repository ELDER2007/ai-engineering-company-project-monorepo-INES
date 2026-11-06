"""Routes of the reporting domain, all under ``/reporting``. HTTP only: every handler calls one function of
``data/pipelines/weekly_office_performance/interface.py`` (no SQL, no ETL here).

* the two reads need a valid session (Laura and Elena are not technical administrators);
* triggering a run needs the ``admin`` role, because it recomputes numbers the leadership reads.

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

router = APIRouter(prefix="/reporting", tags=["reporting"])

TargetDep = Annotated[Engine, Depends(get_reporting_engine)]
SourceDep = Annotated[Engine, Depends(get_telemetry_engine)]


@router.get("/pipeline-runs/latest", response_model=PipelineRunOut, dependencies=[Depends(get_current_user)])
def latest_pipeline_run(engine: TargetDep) -> PipelineRunOut:
    run = interface.get_latest_run(engine)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The pipeline has not run yet")
    return PipelineRunOut(**asdict(run))


@router.post(
    "/pipeline-runs", response_model=PipelineRunOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(admin_only)]
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
    "/weekly-office-program-performance", response_model=WeeklyReport, dependencies=[Depends(get_current_user)]
)
def weekly_office_program_performance(engine: TargetDep, week_start: date | None = Query(default=None)) -> WeeklyReport:
    report = interface.get_weekly_performance(engine, week_start)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No week has been computed yet")
    return WeeklyReport(week_start=report.week_start, entries=[asdict(e) for e in report.entries])
