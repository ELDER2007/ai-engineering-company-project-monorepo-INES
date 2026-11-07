"""The engines the reporting endpoints use, as FastAPI dependencies (tests swap them for throw-away databases)."""

from __future__ import annotations

from sqlalchemy.engine import Engine

from data.pipelines.weekly_office_performance import interface


def get_reporting_engine() -> Engine:
    return interface.reporting_engine()


def get_telemetry_engine() -> Engine:
    return interface.telemetry_engine()


def init_reporting() -> None:
    """Create the ``reporting`` schema and tables if missing (startup)."""
    interface.init_reporting_schema(interface.reporting_engine())
