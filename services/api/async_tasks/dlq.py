"""The dead-letter queue (DLQ): the tasks that failed for good, in the API's own database.

A task that fails is retried (see ``base.py``). When it has used all its attempts it is not retried again and nobody is waiting for it any
more: without a record, it would only exist as a line in a log. This table is that record, one row per task that ended in failure:
``task_id`` (the same id the API gave back), the attempt that failed last, the error and the moment.

It is a table and not a list in Redis on purpose: Redis keeps the queue and the outcomes for a day, with a fixed memory, and it can be
restarted; what failed for good has to outlive all that, and it has to be queried (``SELECT``) by whoever investigates.

The database is the SAME one as the API's (``DATABASE_URL``, or the local SQLite fallback), opened by the worker's own process. The reference SQL is
``sql/001_task_dead_letters.sql``.

**The table has a ``MetaData`` of its own**, not SQLModel's shared one. The inventory creates every table of the shared metadata in its database at
startup (``init_db``): a table declared there would be created there by a module that has nothing to do with the inventory. The same reason why
this module imports nothing that declares tables (``core.redaction``, not ``job_runner``).
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, MetaData, String, Table, Text, create_engine, insert, select
from sqlalchemy.engine import Engine

from core.config import get_database_url
from core.redaction import strip_credentials

logger = logging.getLogger("async_tasks")

MAX_ERROR_LENGTH = 4000
MAX_ARGUMENTS_LENGTH = 1000  # the arguments are light by rule; this only bounds a column
SQLITE_BUSY_TIMEOUT_SECONDS = 30  # the API and the worker may write the same SQLite file: the second waits for the first instead of failing

metadata = MetaData()
dead_letters = Table(
    "task_dead_letters",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("task_id", String(64), nullable=False),  # the id of the task, the one POST returned
    Column("task_name", String(128), nullable=False),
    Column("attempt", Integer, nullable=False),  # the attempt that failed last (1 = the first execution)
    Column("error", Text, nullable=False),  # the message of the error, WITHOUT credentials
    Column("arguments", String(MAX_ARGUMENTS_LENGTH)),  # the light arguments of the task (JSON text)
    Column("failed_at", DateTime(timezone=True), nullable=False),
    Index("ix_task_dead_letters_task_id", "task_id"),
)


@dataclass(frozen=True)
class DeadLetter:
    id: int
    task_id: str
    task_name: str
    attempt: int
    error: str
    arguments: str | None
    failed_at: datetime


def build_engine(url: str | None = None) -> Engine:
    """Engine for ``url`` (default: the API's DATABASE_URL). SQLite is only the local fallback."""
    url = url or get_database_url()
    if url.startswith("sqlite:///"):
        path = url[len("sqlite:///"):]
        return create_engine("sqlite://", creator=lambda: sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS))
    return create_engine(url, pool_pre_ping=True)  # the Supabase pooler closes idle connections


def ensure_table(engine: Engine) -> None:
    """Create ``task_dead_letters`` if it is missing (idempotent)."""
    metadata.create_all(engine)


def record(*, task_id: str, task_name: str, attempt: int, error: str, arguments: str | None = None, engine: Engine | None = None) -> DeadLetter:
    """Write the dead letter. The error is cleaned of credentials first: the message of a database error can carry the URL it was using."""
    engine = engine or build_engine()
    ensure_table(engine)
    values = dict(
        task_id=task_id,
        task_name=task_name,
        attempt=attempt,
        error=strip_credentials(error)[:MAX_ERROR_LENGTH],
        arguments=strip_credentials(arguments)[:MAX_ARGUMENTS_LENGTH] if arguments else None,
        failed_at=datetime.now(timezone.utc),
    )
    with engine.begin() as connection:
        values["id"] = connection.execute(insert(dead_letters).values(**values)).inserted_primary_key[0]
    logger.warning("task=%s task_id=%s status=dead_letter attempt=%d msg=recorded in task_dead_letters", task_name, task_id, attempt)
    return DeadLetter(**values)


def list_dead_letters(limit: int = 50, engine: Engine | None = None) -> list[DeadLetter]:
    """The newest dead letters first."""
    engine = engine or build_engine()
    ensure_table(engine)
    with engine.connect() as connection:
        rows = connection.execute(select(dead_letters).order_by(dead_letters.c.id.desc()).limit(limit)).mappings().all()
    return [DeadLetter(**row) for row in rows]
