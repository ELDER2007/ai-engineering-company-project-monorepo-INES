"""SQL connections of the reporting domain.

Two engines, both resolved lazily so importing the app opens no connection:

* target: the ``reporting`` schema (REPORTING_DATABASE_URL, else DATABASE_URL, else a local SQLite file);
* source: ``telemetry_events``, read-only (TELEMETRY_DATABASE_URL, else DATABASE_URL, else the same local file).
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance import storage


@lru_cache(maxsize=1)
def get_reporting_engine() -> Engine:
    return storage.build_engine(storage.database_url("REPORTING_DATABASE_URL"))


@lru_cache(maxsize=1)
def get_telemetry_engine() -> Engine:
    return storage.build_engine(storage.database_url("TELEMETRY_DATABASE_URL"))


def init_reporting() -> None:
    """Create the ``reporting`` schema and tables if missing (startup)."""
    storage.create_reporting_schema(get_reporting_engine())
