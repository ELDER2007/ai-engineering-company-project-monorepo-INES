"""The connection of the background jobs: the SAME database as the API (``DATABASE_URL``), opened by a process of its own.

Importing this module opens no connection and loads no FastAPI. The URL comes from ``core.config.get_database_url`` (the one the API
uses: the environment, ``services/api/.env``, or the local SQLite fallback), so the job and the API always look at the same store.
"""

from __future__ import annotations

import sqlite3

from sqlalchemy.engine import Engine
from sqlmodel import SQLModel, create_engine

from core.config import get_database_url

from .models import JobRunRow

_SQLITE_PREFIX = "sqlite:///"
SQLITE_BUSY_TIMEOUT_SECONDS = 30  # two processes writing the same SQLite file: the second waits for the first instead of failing


def build_engine(url: str | None = None) -> Engine:
    """Engine for ``url`` (default: the API's DATABASE_URL). SQLite is only the local fallback."""
    url = url or get_database_url()
    if url.startswith(_SQLITE_PREFIX):
        path = url[len(_SQLITE_PREFIX):]
        return create_engine("sqlite://", creator=lambda: sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS))
    return create_engine(url, pool_pre_ping=True)  # the Supabase pooler closes idle connections


def ensure_table(engine: Engine) -> None:
    """Create ``job_runs`` and its indexes if they are missing (idempotent). The reference SQL is ``sql/001_job_runs.sql``."""
    SQLModel.metadata.create_all(engine, tables=[JobRunRow.__table__])
