"""Routes of the reporting domain, all under ``/reporting``.

Same protection as the inventory routes: every route needs a valid session. Handlers are
plain ``def`` so FastAPI runs the blocking SQL (and the Prefect flow) in its thread pool.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.engine import Engine

from auth.dependencies import get_current_user

from . import service
from .database import get_reporting_engine, get_telemetry_engine
from .schemas import PipelineRunCreate, PipelineRunOut, WeeklyReport

router = APIRouter(prefix="/reporting", tags=["reporting"], dependencies=[Depends(get_current_user)])

TargetDep = Annotated[Engine, Depends(get_reporting_engine)]
SourceDep = Annotated[Engine, Depends(get_telemetry_engine)]


@router.get("/weekly-office-program-performance", response_model=WeeklyReport)
def weekly_office_program_performance(
    engine: TargetDep, week_start: date | None = Query(default=None)
) -> WeeklyReport:
    report = service.get_weekly_report(engine, week_start)
    if report is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No week has been computed yet")
    return report


@router.get("/pipeline-runs/latest", response_model=PipelineRunOut)
def latest_pipeline_run(engine: TargetDep) -> PipelineRunOut:
    run = service.get_latest_run(engine)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The pipeline has not run yet")
    return run


@router.post("/pipeline-runs", response_model=PipelineRunOut, status_code=status.HTTP_201_CREATED)
def trigger_pipeline_run(
    target: TargetDep, source: SourceDep, body: Annotated[PipelineRunCreate, Body()] = PipelineRunCreate()
) -> PipelineRunOut:
    try:
        return service.run_pipeline(target, source, body.week_start)
    except Exception as exc:  # the flow already recorded the failed run
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Pipeline run failed: {exc}") from exc
