"""Prefect flow + tasks of the weekly office/programme performance pipeline.

Orchestration only: the transformation logic is in ``data/process/weekly_performance.py``
(pure functions), the SQL in ``storage.py``. See ../PIPELINE_DESIGN.md, section 4.

Engines are not Prefect parameters (they are not serialisable): the flow resolves them from
the environment, and tests/the API can pass ready-made ones. Tasks use ``NO_CACHE`` for the
same reason. Connection strings should move to Prefect ``Secret`` blocks once a Prefect
server is deployed (design, section 4.5).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from prefect import flow, get_run_logger, task
from prefect.cache_policies import NO_CACHE
from sqlalchemy import select
from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance import storage
from data.process import weekly_performance as wp

FLOW_NAME = "weekly-office-performance"
STATE_COMPLETED, STATE_FAILED = "Completed", "Failed"

_log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- tasks


@task(cache_policy=NO_CACHE)
def resolve_week_window(week_start: date | None) -> tuple[date, datetime, datetime]:
    return wp.resolve_week_window(week_start)


@task(cache_policy=NO_CACHE, retries=3, retry_delay_seconds=[5, 30, 120])
def extract_events(source: Engine, start: datetime, end: datetime) -> list[wp.TelemetryEvent]:
    """Read-only SELECT of the four event types in ``[start, end)``."""
    te = storage.telemetry_events
    query = select(te.c.event_type, te.c.occurred_at, te.c.properties).where(
        te.c.event_type.in_(wp.EVENT_TYPES), te.c.occurred_at >= start, te.c.occurred_at < end
    )
    with source.connect() as connection:
        rows = connection.execute(query).all()
    return [wp.TelemetryEvent(r.event_type, wp.ensure_utc(r.occurred_at), r.properties or {}) for r in rows]


@task(cache_policy=NO_CACHE)
def validate_events(events: list[wp.TelemetryEvent]) -> wp.ValidationResult:
    result = wp.validate_events(events)
    for rejected in result.rejected:
        get_run_logger().warning("rejected %s: %s", rejected.event.event_type, rejected.reason)
    return result


@task(cache_policy=NO_CACHE)
def check_currency_consistency(events: list[wp.CleanEvent]) -> None:
    wp.check_currency_consistency(events)


@task(cache_policy=NO_CACHE)
def aggregate_by_office_programme(events: list[wp.CleanEvent], week_start: date) -> list[wp.WeeklyRow]:
    return wp.aggregate_by_office_programme(events, week_start)


@task(cache_policy=NO_CACHE, retries=3, retry_delay_seconds=[5, 30, 120])
def load_weekly_performance(target: Engine, rows: list[wp.WeeklyRow]) -> int:
    """Idempotent UPSERT on ``unique (office, programme_id, week_start)``."""
    if not rows:
        return 0
    now = datetime.now(timezone.utc)
    table = storage.weekly_performance
    if target.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    values = [
        {
            "id": uuid.uuid4(),
            "office": r.office,
            "programme_id": r.programme_id,
            "week_start": r.week_start,
            "total_material_cost": r.total_material_cost,
            "kits_delivered_count": r.kits_delivered_count,
            "shortage_events_count": r.shortage_events_count,
            "cost_variance_events_count": r.cost_variance_events_count,
            "currency": r.currency,
            "computed_at": now,
        }
        for r in rows
    ]
    statement = insert(table).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=list(storage.UPSERT_CONFLICT_COLUMNS),
        set_={
            name: statement.excluded[name]
            for name in (
                "total_material_cost",
                "kits_delivered_count",
                "shortage_events_count",
                "cost_variance_events_count",
                "currency",
                "computed_at",
            )
        },
    )
    with target.begin() as connection:
        connection.execute(statement)
    return len(values)


@task(cache_policy=NO_CACHE)
def record_pipeline_run(target: Engine, run: dict[str, Any]) -> None:
    with target.begin() as connection:
        connection.execute(storage.pipeline_runs.insert().values(**run))


# --------------------------------------------------------------------------- flow


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    state: str
    week_start: date | None
    events_read: int
    rejected_count: int
    rows_written: int
    error: str | None


@flow(name=FLOW_NAME, validate_parameters=False)
def weekly_office_performance_flow(
    week_start: date | None = None,
    trigger: str = "scheduled",
    source_engine: Engine | None = None,
    target_engine: Engine | None = None,
) -> RunSummary:
    """Compute and load the weekly report for ``week_start`` (default: last complete ISO week).

    A failure is recorded in ``reporting.pipeline_runs`` and then re-raised, so the Prefect
    run ends ``Failed`` and ``GET /reporting/pipeline-runs/latest`` shows it.
    """
    target = target_engine or storage.build_engine(storage.database_url("REPORTING_DATABASE_URL"))
    source = source_engine or storage.build_engine(storage.database_url("TELEMETRY_DATABASE_URL"))
    storage.create_reporting_schema(target)

    started_at = datetime.now(timezone.utc)
    resolved_week: date | None = None
    events_read = rejected = written = 0
    try:
        resolved_week, start, end = resolve_week_window(week_start)
        events = extract_events(source, start, end)
        events_read = len(events)
        checked = validate_events(events)
        rejected = len(checked.rejected)
        check_currency_consistency(checked.valid)
        rows = aggregate_by_office_programme(checked.valid, resolved_week)
        written = load_weekly_performance(target, rows)
        error, state = None, STATE_COMPLETED
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised below
        error, state = f"{type(exc).__name__}: {exc}", STATE_FAILED
        raised: Exception | None = exc
    else:
        raised = None

    run = {
        "id": uuid.uuid4(),
        "flow_name": FLOW_NAME,
        "trigger": trigger,
        "state": state,
        "week_start": resolved_week,
        "events_read": events_read,
        "rejected_count": rejected,
        "rows_written": written,
        "error": error,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc),
    }
    record_pipeline_run(target, run)
    if raised is not None:
        raise raised
    return RunSummary(str(run["id"]), state, resolved_week, events_read, rejected, written, None)
