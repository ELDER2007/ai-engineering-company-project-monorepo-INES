"""Storage of the pipeline: the read-only telemetry source and the ``reporting`` schema.

* ``telemetry_events`` is only ever *read* (SELECT). It is owned by the telemetry domain
  (``services/api/telemetry/models.py``); the definition below mirrors its real columns and is used to build the
  queries and, for local demos only, to create a throw-away copy. The pipeline never writes to it in production.
* Everything the pipeline writes lives under the dedicated ``reporting`` schema.

PostgreSQL/Supabase is the real target. SQLite is the local fallback: since SQLite has no schemas, ``reporting`` is
emulated by attaching a second database file under that name, so the same ``reporting.<table>`` SQL runs on both.

Engines are built from connection strings here, and passed in by callers; nothing imports from ``services/``.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import (
    JSON,
    Column,
    Date,
    DateTime,
    Index,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

REPORTING_SCHEMA = "reporting"
_SQLITE_PREFIX = "sqlite:///"
DEFAULT_ENVIRONMENT = "production"

# Read-only mirror of services/api/telemetry/models.py (8 columns). `tags` is the event's `properties`.
source_metadata = MetaData()
telemetry_events = Table(
    "telemetry_events",
    source_metadata,
    Column("event_id", String(36), primary_key=True),
    Column("event_type", String(64), nullable=False, index=True),
    Column("timestamp", DateTime(timezone=True), nullable=False, index=True),
    Column("service", String(16), nullable=False),
    Column("user_id", String(64)),
    Column("session_id", String(36)),
    Column("environment", String(16), nullable=False),
    Column("tags", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
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

# One row per run (the execution log, PIPELINE_DESIGN.md section 5.2).
pipeline_runs = Table(
    "pipeline_runs",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("flow_name", String, nullable=False),
    Column("trigger", String, nullable=False),  # scheduled | manual
    Column("prefect_flow_run_id", String),
    Column("week_start", Date, nullable=False),
    Column("environment", String, nullable=False),  # which telemetry environment was read
    Column("state", String, nullable=False),  # Running | Completed | Failed | Crashed | Skipped
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True)),
    Column("events_read", Integer, nullable=False, default=0),
    Column("window_events_total", Integer, nullable=False, default=0),
    Column("rejected_count", Integer, nullable=False, default=0),
    Column("rows_written", Integer, nullable=False, default=0),
    Column("rows_changed", Integer, nullable=False, default=0),
    Column("rows_deleted", Integer, nullable=False, default=0),
    Column("error", String),
    # The lock: the database itself refuses a second `Running` run of the same week (no check-then-insert race).
    Index(
        "uq_pipeline_runs_one_running_per_week",
        "flow_name",
        "week_start",
        unique=True,
        sqlite_where=text("state = 'Running'"),
        postgresql_where=text("state = 'Running'"),
    ),
)

UPSERT_CONFLICT_COLUMNS = ("office", "programme_id", "week_start")


def app_local_url() -> str:
    """The SQLite file the API uses when DATABASE_URL is not set (where its telemetry lives in local development)."""
    return f"{_SQLITE_PREFIX}{Path(__file__).resolve().parents[3] / 'services' / 'api' / 'inventory' / 'db.sqlite'}"


def demo_url() -> str:
    """A throw-away SQLite file for ``--demo`` runs: never the app's own database."""
    path = Path(__file__).resolve().parents[2] / ".local" / "demo.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"{_SQLITE_PREFIX}{path}"


def database_url(env: str = "DATABASE_URL") -> str:
    """Connection string: ``env``, else DATABASE_URL, else the API's local SQLite file."""
    raw = os.environ.get(env, "").strip() or os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return app_local_url()
    for scheme in ("postgres://", "postgresql://"):
        if raw.startswith(scheme):
            return "postgresql+psycopg2://" + raw[len(scheme):]
    return raw


def default_environment() -> str:
    """Telemetry environment to report on (PIPELINE_ENVIRONMENT, default ``production``): test and development
    events must never reach a report the CEO reads."""
    return os.environ.get("PIPELINE_ENVIRONMENT", "").strip() or DEFAULT_ENVIRONMENT


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
