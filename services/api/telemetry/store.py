"""Persistence of the telemetry events: append-only (no update, no delete) and deduplicated by ``eventId``.

The receiver validates and stamps; this module only stores what it is given. It never validates (the contract did) and never
updates a row.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.dialects import postgresql, sqlite
from sqlmodel import Session

from .models import TelemetryEventRow

logger = logging.getLogger("telemetry")


def to_row(event: dict[str, Any]) -> dict[str, Any]:
    """The column values of one validated, stamped event (``TelemetryEvent.model_dump(mode="json")``). The envelope's
    ``properties`` goes whole into ``tags``; ``requestId`` and ``schemaVersion`` are not columns of the table."""
    return {
        "event_id": event["eventId"],
        "event_type": event["event_type"],
        # "Z" is not parsed by fromisoformat before Python 3.11
        "timestamp": datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")).astimezone(timezone.utc),
        "service": event["source"],
        "user_id": event["userId"],
        "session_id": event["sessionId"],
        "environment": event["environment"],
        "tags": event["properties"],
    }


def save(session: Session, events: list[dict[str, Any]]) -> int:
    """Insert ``events`` in ONE statement and one transaction and return how many were NEW. An ``eventId`` already stored is
    skipped without error: a delivery retry carries the same id (at-least-once delivery) and must count once. Raises on a database
    failure, so the caller does not acknowledge what was not stored."""
    if not events:
        return 0
    rows = [to_row(event) for event in events]
    insert = (postgresql if session.get_bind().dialect.name == "postgresql" else sqlite).insert
    statement = insert(TelemetryEventRow).values(rows).on_conflict_do_nothing(index_elements=["event_id"]).returning(TelemetryEventRow.event_id)
    try:
        inserted = len(session.execute(statement).all())
        session.commit()
    except Exception:
        session.rollback()
        raise
    if inserted < len(rows):
        logger.info("%d duplicate event(s) skipped (delivery retry)", len(rows) - inserted)
    return inserted
