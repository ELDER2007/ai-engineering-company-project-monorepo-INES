"""ORM table of the background jobs' control log (SQLModel), in the same SQL store as ``telemetry_events`` and the inventory.

One table: ``job_runs``. One row per EXECUTION of a background job (today: ``nightly_export``), whatever its outcome. It is the
orchestration layer's log: it says what the NIGHT did (export the CSV, launch the pipeline) and whether it finished. It is NOT
``pipeline_runs`` (the ETL's own log of its phases): the script writes this one, the pipeline writes that one, and neither reads
the other to decide anything.

The status is a state machine::

    pending -> processing -> completed
                         \\-> failed

* ``pending``: the row exists, the work has not started. Created BEFORE anything is done.
* ``processing``: set at the start of the work, before doing any of it. This state IS the lock (see below).
* ``completed`` / ``failed``: the end. ``failed`` carries ``error_message``.

THE LOCK IS THE STATE ITSELF. There is no lock table, lock column or lock file. What makes "at most one ``processing`` row per job" true
even when two processes start at the same instant is a constraint of the database on that same column: a PARTIAL UNIQUE INDEX on
``job_name`` where ``status = 'processing'``. A second row that tries to become ``processing`` is rejected by the database, not by a
check the application did a moment before (which two processes can pass at the same time).

``(job_name, target_date)`` has a plain (not unique) index: it answers "is that day already done?" quickly, and it must not be unique
because every execution is recorded, so a day that failed can be tried again.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CheckConstraint, Index, Text, text
from sqlmodel import DateTime, Field, SQLModel

PENDING = "pending"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"
STATUSES = (PENDING, PROCESSING, COMPLETED, FAILED)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRunRow(SQLModel, table=True):
    __tablename__ = "job_runs"
    __table_args__ = (
        CheckConstraint("status in ('pending', 'processing', 'completed', 'failed')", name="ck_job_runs_status"),
        Index("ix_job_runs_job_name_target_date", "job_name", "target_date"),
        # The lock: one row in ``processing`` per job, enforced by the database. Partial indexes exist in PostgreSQL and in SQLite.
        Index("uq_job_runs_one_processing_per_job", "job_name", unique=True,
              postgresql_where=text("status = 'processing'"), sqlite_where=text("status = 'processing'")),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    job_name: str = Field(max_length=64)  # which job: "nightly_export"
    target_date: date  # the day the run is about (UTC); what makes the job idempotent PER DAY
    status: str = Field(default=PENDING, max_length=16)
    started_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # when it became ``processing``
    finished_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # when it became completed or failed
    error_message: str | None = Field(default=None, sa_type=Text)  # the exception's message, with no credential in it
    created_at: datetime = Field(default_factory=utcnow, sa_type=DateTime(timezone=True))
