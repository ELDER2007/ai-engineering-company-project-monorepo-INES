"""Storage of the pipeline: the read-only telemetry source and the ``reporting`` schema.

* ``telemetry_events`` is only ever *read* (SELECT). The table is owned by the telemetry domain.
* Everything the pipeline writes lives under the dedicated ``reporting`` schema.

PostgreSQL/Supabase is the real target. SQLite is the local fallback (same idea as the
inventory domain): since SQLite has no schemas, ``reporting`` is emulated by attaching a
second database file under that name, so the very same ``reporting.<table>`` SQL runs on both.

Engines are always passed in by the caller; nothing here imports from ``services/``.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine

REPORTING_SCHEMA = "reporting"
_SQLITE_PREFIX = "sqlite:///"

# Read-only view of the source. Only the columns the pipeline needs.
# ASSUMPTION (see PIPELINE_DESIGN.md, open questions): telemetry_events has these columns.
source_metadata = MetaData()
telemetry_events = Table(
    "telemetry_events",
    source_metadata,
    Column("event_type", String, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("properties", JSON, nullable=False),
)

metadata = MetaData(schema=REPORTING_SCHEMA)

weekly_performance = Table(
    "weekly_office_program_performance",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("office", String, nullable=False),
    Column("programme_id", String, nullable=False),
    Column("week_start", Date, nullable=False),
    Column("total_material_cost", Numeric(18, 2), nullable=False, default=0),
    Column("kits_delivered_count", Integer, nullable=False, default=0),
    Column("shortage_events_count", Integer, nullable=False, default=0),
    Column("cost_variance_events_count", Integer, nullable=False, default=0),
    Column("currency", String, nullable=False),
    Column("computed_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint("office", "programme_id", "week_start", name="uq_weekly_office_program_week"),
)

pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("flow_name", String, nullable=False),
    Column("trigger", String, nullable=False),  # "scheduled" | "manual"
    Column("state", String, nullable=False),  # "Completed" | "Failed"
    Column("week_start", Date, nullable=True),
    Column("events_read", Integer, nullable=False, default=0),
    Column("rejected_count", Integer, nullable=False, default=0),
    Column("rows_written", Integer, nullable=False, default=0),
    Column("error", String, nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=False),
)

UPSERT_CONFLICT_COLUMNS = ("office", "programme_id", "week_start")


def default_local_url() -> str:
    """SQLite file used when no DATABASE_URL is configured (gitignored)."""
    path = Path(__file__).resolve().parents[2] / ".local" / "pipeline.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{_SQLITE_PREFIX}{path}"


def database_url(env: str = "DATABASE_URL") -> str:
    """Connection string from the environment, with the same fallback the API uses."""
    raw = os.environ.get(env, "").strip() or os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return default_local_url()
    for scheme in ("postgres://", "postgresql://"):
        if raw.startswith(scheme):
            return "postgresql+psycopg2://" + raw[len(scheme):]
    return raw


def build_engine(url: str) -> Engine:
    """Engine for ``url``. On SQLite, attach the ``reporting`` database on every connection."""
    if not url.startswith(_SQLITE_PREFIX):
        return create_engine(url, pool_pre_ping=True)
    engine = create_engine(url)
    reporting_file = url[len(_SQLITE_PREFIX):] + ".reporting"

    @event.listens_for(engine, "connect")
    def _attach(dbapi_connection, _record):  # noqa: ANN001
        dbapi_connection.execute(f"ATTACH DATABASE '{reporting_file}' AS {REPORTING_SCHEMA}")

    return engine


def create_reporting_schema(engine: Engine) -> None:
    """Create the ``reporting`` schema and its tables if missing (idempotent).

    On PostgreSQL the reference DDL is ``sql/001_reporting_schema.sql``; this mirrors it.
    """
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text(f"create schema if not exists {REPORTING_SCHEMA}"))
    metadata.create_all(engine)
