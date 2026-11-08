"""The state machine of the background jobs: create, move and query ``job_runs``.

This is the ONLY place that knows how a row changes state. A job (``scripts/nightly_export.py``) gives orders and never writes a
status by itself. Every function takes a SQLModel ``Session`` and commits what it changes, so the state is on disk the moment the
call returns: another process sees it.

No FastAPI here, and nothing that needs it: a background job must be a process of its own.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from .models import COMPLETED, FAILED, PENDING, PROCESSING, JobRunRow, utcnow

MAX_ERROR_LENGTH = 2000
_CREDENTIALS = re.compile(r"([a-z][a-z0-9+.-]*://)[^\s/@]*@", re.IGNORECASE)  # scheme://user:password@host -> scheme://***@host


class JobAlreadyRunning(RuntimeError):
    """Another run of the same job is in ``processing``: this one must not start."""


class InvalidTransition(RuntimeError):
    """The row is not in a state from which the requested change is allowed."""


def strip_credentials(text: str) -> str:
    """``text`` without the user and password of any connection URL (``scheme://user:password@host`` -> ``scheme://***@host``)."""
    return _CREDENTIALS.sub(r"\1***@", str(text))


def redact(text: str) -> str:
    """``strip_credentials`` and cut to a size a column can hold. The message of a database error can carry the URL it was
    connecting to: it must never reach ``error_message`` or a log."""
    return strip_credentials(text)[:MAX_ERROR_LENGTH]


def _aware(value: datetime | None) -> datetime | None:
    """SQLite gives back naive datetimes: every date this module stores is UTC, so a naive one is UTC."""
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------------------------------------ writes: the transitions


def create_job_run(session: Session, job_name: str, target_date: date) -> JobRunRow:
    """A new row in ``pending``: the run exists before it does any work."""
    row = JobRunRow(job_name=job_name, target_date=target_date, status=PENDING)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def start_processing(session: Session, run_id: uuid.UUID) -> JobRunRow:
    """``pending`` -> ``processing``: the run takes the lock. Atomic, and decided by the DATABASE.

    If another run of the same job is already ``processing``, the unique partial index refuses this change and
    ``JobAlreadyRunning`` is raised, even if both runs asked at the very same instant."""
    try:
        result = session.execute(
            update(JobRunRow).where(JobRunRow.id == run_id, JobRunRow.status == PENDING).values(status=PROCESSING, started_at=utcnow())
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise JobAlreadyRunning("another run of this job is already processing") from error
    if result.rowcount != 1:
        raise InvalidTransition(f"run {run_id} is not pending: it cannot start")
    return _get(session, run_id)


def complete(session: Session, run_id: uuid.UUID) -> JobRunRow:
    """``processing`` -> ``completed``: the lock is released."""
    result = session.execute(
        update(JobRunRow).where(JobRunRow.id == run_id, JobRunRow.status == PROCESSING).values(status=COMPLETED, finished_at=utcnow())
    )
    session.commit()
    if result.rowcount != 1:
        raise InvalidTransition(f"run {run_id} is not processing: it cannot be completed")
    return _get(session, run_id)


def fail(session: Session, run_id: uuid.UUID, error_message: str) -> bool:
    """``pending`` or ``processing`` -> ``failed``, with the message of the error (cleaned of credentials). The lock is released.
    ``False`` if the run was already finished: failing a finished run changes nothing."""
    result = session.execute(
        update(JobRunRow).where(JobRunRow.id == run_id, JobRunRow.status.in_((PENDING, PROCESSING)))
        .values(status=FAILED, finished_at=utcnow(), error_message=redact(error_message))
    )
    session.commit()
    return result.rowcount == 1


def discard_pending(session: Session, run_id: uuid.UUID) -> bool:
    """Remove a run that never started. The instance that finds the lock taken leaves NO trace in the table: a row left in
    ``pending`` by an instance that went away would be a zombie."""
    result = session.execute(delete(JobRunRow).where(JobRunRow.id == run_id, JobRunRow.status == PENDING))
    session.commit()
    return result.rowcount == 1


def mark_stale_as_failed(session: Session, job_name: str, older_than: timedelta, now: datetime | None = None) -> list[uuid.UUID]:
    """Close as ``failed`` the runs of ``job_name`` that can only be dead: ``processing`` for longer than ``older_than``, or
    ``pending`` that never started in that time.

    A process that is killed (``kill -9``, a power cut, a restarted server) cannot write its own ``failed``, and its ``processing``
    row would block every later night for ever. The next run calls this first. ``older_than`` must be longer than the longest
    honest run."""
    cutoff = (now or utcnow()) - older_than
    stale = session.execute(
        select(JobRunRow.id, JobRunRow.status).where(
            JobRunRow.job_name == job_name,
            ((JobRunRow.status == PROCESSING) & (JobRunRow.started_at < cutoff)) | ((JobRunRow.status == PENDING) & (JobRunRow.created_at < cutoff)),
        )
    ).all()
    closed = []
    for run_id, status in stale:
        reason = (f"stale: it was processing for more than {older_than} and the process that held it is gone"
                  if status == PROCESSING else f"stale: it was pending for more than {older_than} and never started")
        if fail(session, run_id, reason):
            closed.append(run_id)
    return closed


# ------------------------------------------------------------------------------------------------ reads


def has_processing_lock(session: Session, job_name: str) -> bool:
    """Is there a run of ``job_name`` in ``processing``? A quick way to give up early. NOT the lock itself: between asking and
    starting another process can slip in, which is why ``start_processing`` is what the database enforces."""
    return session.execute(select(func.count()).select_from(JobRunRow).where(JobRunRow.job_name == job_name, JobRunRow.status == PROCESSING)).scalar_one() > 0


def has_completed_for_date(session: Session, job_name: str, target_date: date) -> bool:
    """Is that day already done? The idempotency check: always by day, because the ``completed`` of yesterday says nothing about today."""
    return session.execute(
        select(func.count()).select_from(JobRunRow).where(JobRunRow.job_name == job_name, JobRunRow.target_date == target_date, JobRunRow.status == COMPLETED)
    ).scalar_one() > 0


def list_runs(session: Session, job_name: str | None = None, limit: int = 20) -> list[JobRunRow]:
    """The latest runs, newest first."""
    query = select(JobRunRow).order_by(JobRunRow.created_at.desc()).limit(limit)
    if job_name:
        query = query.where(JobRunRow.job_name == job_name)
    return list(session.execute(query).scalars())


def latest(session: Session, job_name: str) -> JobRunRow | None:
    runs = list_runs(session, job_name, limit=1)
    return runs[0] if runs else None


def _get(session: Session, run_id: uuid.UUID) -> JobRunRow:
    session.expire_all()
    row = session.get(JobRunRow, run_id)
    if row is None:
        raise InvalidTransition(f"run {run_id} does not exist")
    row.started_at, row.finished_at, row.created_at = _aware(row.started_at), _aware(row.finished_at), _aware(row.created_at)
    return row
