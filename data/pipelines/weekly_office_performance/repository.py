"""All the SQL of the pipeline, in one place: read the events, load the results, keep the execution log.

``pipeline.py`` (the Prefect tasks) and ``interface.py`` (what ``services/`` may call) use these functions; no SQL
lives anywhere else. The only table read from the telemetry domain is ``telemetry_events``, with SELECT.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError

from data.pipelines.weekly_office_performance import storage
from data.process import weekly_performance as wp

STATE_RUNNING, STATE_COMPLETED, STATE_FAILED = "Running", "Completed", "Failed"
STATE_CRASHED, STATE_SKIPPED = "Crashed", "Skipped"
STALE_AFTER = timedelta(hours=1)  # a Running run older than this is a dead run

_te = storage.telemetry_events
_perf = storage.weekly_performance
_runs = storage.pipeline_runs
_KPI_COLUMNS = ("total_material_cost", "kits_delivered_count", "shortage_events_count", "cost_variance_events_count", "currency")


@dataclass(frozen=True)
class WeeklyEntry:
    office: str
    programme_id: str
    total_material_cost: float
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: str


@dataclass(frozen=True)
class WeeklyReport:
    week_start: date
    entries: list[WeeklyEntry]


@dataclass(frozen=True)
class RunInfo:
    id: str
    flow_name: str
    trigger: str
    prefect_flow_run_id: str | None
    week_start: date
    environment: str
    state: str
    started_at: datetime
    finished_at: datetime | None
    events_read: int
    window_events_total: int | None
    rejected_count: int
    rows_written: int
    rows_changed: int
    rows_deleted: int
    error: str | None
    warnings: str | None


@dataclass(frozen=True)
class LoadResult:
    written: int
    changed: int
    deleted: int


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- extract (read-only)


def _window(start: datetime, end: datetime, environment: str):
    return and_(_te.c.timestamp >= start, _te.c.timestamp < end, _te.c.environment == environment)


def extract(source: Engine, start: datetime, end: datetime, environment: str) -> list[wp.TelemetryEvent]:
    """SELECT the four business event types of ``[start, end)`` in ``environment`` (indexed columns). Never writes."""
    query = select(_te.c.event_id, _te.c.event_type, _te.c.timestamp, _te.c.tags).where(
        _window(start, end, environment), _te.c.event_type.in_(wp.EVENT_TYPES)
    )
    with source.connect() as connection:
        rows = connection.execute(query).all()
    return [wp.TelemetryEvent(r.event_type, wp.ensure_utc(r.timestamp), r.tags or {}, r.event_id) for r in rows]


def count_window_events(source: Engine, start: datetime, end: datetime, environment: str) -> int:
    """Events of ANY type in the window: the liveness signal of the capture (a real zero vs a dead capture)."""
    with source.connect() as connection:
        return connection.execute(select(func.count()).select_from(_te).where(_window(start, end, environment))).scalar_one()


# --------------------------------------------------------------------------- load (one transaction)


def _verify_load(connection: Connection, week_start: date, expected: int) -> None:
    """After writing, the week must hold exactly the rows that were computed; otherwise the caller rolls back."""
    stored = connection.execute(select(func.count()).select_from(_perf).where(_perf.c.week_start == week_start)).scalar_one()
    if stored != expected:
        raise RuntimeError(f"load check failed: {stored} rows stored for {week_start}, {expected} computed")


def _insert_for(engine: Engine):
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert


def load_week(target: Engine, rows: list[wp.WeeklyRow], week_start: date) -> LoadResult:
    """Replace the week in ONE transaction: upsert every row (replace, never add), delete the rows of the week that
    no longer have events, verify the count. Any failure rolls the whole week back, so the table keeps what the last
    good load left."""
    now = _now()
    with target.begin() as connection:
        existing = {
            (r["office"], r["programme_id"]): r
            for r in connection.execute(select(_perf).where(_perf.c.week_start == week_start)).mappings()
        }
        new_keys = {(r.office, r.programme_id) for r in rows}

        changed = 0
        for r in rows:
            old = existing.get((r.office, r.programme_id))
            if old is not None and any(
                Decimal(old[c]) != getattr(r, c) if c == "total_material_cost" else old[c] != getattr(r, c) for c in _KPI_COLUMNS
            ):
                changed += 1

        if rows:
            insert = _insert_for(target)
            statement = insert(_perf).values(
                [
                    {
                        "id": uuid.uuid4(),
                        "office": r.office,
                        "programme_id": r.programme_id,
                        "week_start": r.week_start,
                        **{c: getattr(r, c) for c in _KPI_COLUMNS},
                        "computed_at": now,
                    }
                    for r in rows
                ]
            )
            # IDEMPOTENT UPSERT on the briefing's unique constraint (office, programme_id, week_start):
            #  - no row for that key yet  -> INSERT;
            #  - a row exists             -> REPLACE its KPIs (never add to them), but ONLY IF one of them differs.
            # The WHERE makes a repeated run a true no-op: the row (id and computed_at included) is not even touched, so
            # the table after two runs over the same data is identical to the table after one. ``computed_at`` therefore
            # means "when these values were last computed or changed".
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=list(storage.UPSERT_CONFLICT_COLUMNS),
                    set_={c: statement.excluded[c] for c in (*_KPI_COLUMNS, "computed_at")},
                    where=or_(*[_perf.c[c].is_distinct_from(statement.excluded[c]) for c in _KPI_COLUMNS]),
                )
            )

        stale = [key for key in existing if key not in new_keys]
        if stale:
            connection.execute(
                delete(_perf).where(
                    _perf.c.week_start == week_start,
                    or_(*[and_(_perf.c.office == o, _perf.c.programme_id == p) for o, p in stale]),
                )
            )
        _verify_load(connection, week_start, len(rows))
    return LoadResult(written=len(rows), changed=changed, deleted=len(stale))


# --------------------------------------------------------------------------- results (read, for the API)


def latest_week(engine: Engine) -> date | None:
    with engine.connect() as connection:
        return connection.execute(select(func.max(_perf.c.week_start))).scalar()


def get_weekly_report(engine: Engine, week_start: date | None) -> WeeklyReport | None:
    """The office/programme rows of ``week_start`` (default: the latest computed week); ``None`` when nothing was ever computed."""
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


# --------------------------------------------------------------------------- the execution log


def _run_info(row) -> RunInfo:  # noqa: ANN001
    data = dict(row)
    data["id"] = str(data["id"])
    return RunInfo(**{k: data[k] for k in RunInfo.__dataclass_fields__})


def mark_stale_runs(engine: Engine, flow_name: str) -> int:
    """A ``Running`` run older than one hour died without closing its log: mark it ``Crashed`` so it cannot lock the week."""
    limit = _now() - STALE_AFTER
    with engine.begin() as connection:
        result = connection.execute(
            update(_runs)
            .where(_runs.c.flow_name == flow_name, _runs.c.state == STATE_RUNNING, _runs.c.started_at < limit)
            .values(state=STATE_CRASHED, finished_at=_now(), error="marked Crashed: no result after 1 hour")
        )
    return result.rowcount


def mark_crashed_by_prefect_id(engine: Engine, prefect_flow_run_id: str, reason: str) -> int:
    """Close the ``Running`` row of a Prefect flow run that crashed (the process or its infrastructure died)."""
    with engine.begin() as connection:
        result = connection.execute(
            update(_runs)
            .where(_runs.c.prefect_flow_run_id == prefect_flow_run_id, _runs.c.state == STATE_RUNNING)
            .values(state=STATE_CRASHED, finished_at=_now(), error=reason)
        )
    return result.rowcount


def start_run(
    engine: Engine, *, flow_name: str, trigger: str, week_start: date, environment: str, prefect_flow_run_id: str | None
) -> tuple[str, bool]:
    """Open the run as ``Running``. Returns ``(run_id, True)``; or, when the week is already being run (the database's
    partial unique index refuses a second ``Running``), records a ``Skipped`` row and returns ``(run_id, False)``."""
    mark_stale_runs(engine, flow_name)
    base = dict(
        flow_name=flow_name, trigger=trigger, week_start=week_start, environment=environment,
        prefect_flow_run_id=prefect_flow_run_id, started_at=_now(),
    )
    run_id = uuid.uuid4()
    try:
        with engine.begin() as connection:
            connection.execute(_runs.insert().values(id=run_id, state=STATE_RUNNING, **base))
        return str(run_id), True
    except IntegrityError:
        run_id = uuid.uuid4()
        with engine.begin() as connection:
            connection.execute(
                _runs.insert().values(
                    id=run_id, state=STATE_SKIPPED, finished_at=_now(), error="another run of this week is already running", **base
                )
            )
        return str(run_id), False


def finish_run(engine: Engine, run_id: str, **fields) -> None:
    """Close the run: final state, counts, error, ``finished_at``."""
    with engine.begin() as connection:
        connection.execute(update(_runs).where(_runs.c.id == uuid.UUID(run_id)).values(finished_at=_now(), **fields))


def get_run(engine: Engine, run_id: str) -> RunInfo | None:
    with engine.connect() as connection:
        row = connection.execute(select(_runs).where(_runs.c.id == uuid.UUID(run_id))).mappings().first()
    return _run_info(row) if row else None


def get_latest_run(engine: Engine) -> RunInfo | None:
    with engine.connect() as connection:
        row = connection.execute(select(_runs).order_by(_runs.c.started_at.desc()).limit(1)).mappings().first()
    return _run_info(row) if row else None
