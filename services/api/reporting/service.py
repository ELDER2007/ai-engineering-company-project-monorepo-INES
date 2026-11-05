"""Queries over the ``reporting`` schema and the trigger of the pipeline."""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance import storage
from data.pipelines.weekly_office_performance.flow import weekly_office_performance_flow

from .schemas import PipelineRunOut, WeeklyEntry, WeeklyReport

_perf = storage.weekly_performance
_runs = storage.pipeline_runs


def latest_week(engine: Engine) -> date | None:
    with engine.connect() as connection:
        return connection.execute(select(func.max(_perf.c.week_start))).scalar()


def get_weekly_report(engine: Engine, week_start: date | None) -> WeeklyReport | None:
    """All office/programme rows of ``week_start`` (default: the latest computed week).

    ``None`` when no week was ever computed and none was asked for.
    """
    week = week_start or latest_week(engine)
    if week is None:
        return None
    query = select(_perf).where(_perf.c.week_start == week).order_by(_perf.c.office, _perf.c.programme_id)
    with engine.connect() as connection:
        rows = connection.execute(query).mappings().all()
    return WeeklyReport(
        week_start=week,
        entries=[
            WeeklyEntry(
                office=r["office"],
                programme_id=r["programme_id"],
                total_material_cost=float(r["total_material_cost"]),
                kits_delivered_count=r["kits_delivered_count"],
                shortage_events_count=r["shortage_events_count"],
                cost_variance_events_count=r["cost_variance_events_count"],
                currency=r["currency"],
            )
            for r in rows
        ],
    )


def get_latest_run(engine: Engine) -> PipelineRunOut | None:
    query = select(_runs).order_by(_runs.c.started_at.desc()).limit(1)
    with engine.connect() as connection:
        row = connection.execute(query).mappings().first()
    return _run_out(row) if row else None


def run_pipeline(target: Engine, source: Engine, week_start: date | None) -> PipelineRunOut:
    """Run the Prefect flow now (manual trigger) and return the run it recorded.

    A failing run is recorded by the flow itself and re-raised here.
    """
    weekly_office_performance_flow(
        week_start=week_start, trigger="manual", source_engine=source, target_engine=target
    )
    run = get_latest_run(target)
    assert run is not None  # the flow always records its run
    return run


def _run_out(row) -> PipelineRunOut:  # noqa: ANN001
    return PipelineRunOut(**{**dict(row), "id": str(row["id"])})
