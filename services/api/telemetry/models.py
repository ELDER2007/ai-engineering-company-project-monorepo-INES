"""ORM table of the telemetry storage (SQLModel), in the same SQL store as the inventory (Supabase/PostgreSQL, or the local SQLite).

One table, immutable: ``telemetry_events``. Eight columns, one row per validated event:

* ``event_id`` (primary key): the envelope's ``eventId``, the key to deduplicate delivery retries by;
* ``event_type``, ``timestamp`` and ``service`` (the envelope's ``source``): the fixed columns analytical queries rely on;
* ``user_id`` (the HMAC pseudonym, never the operational id), ``session_id`` and ``environment``: the rest of the identity;
* ``tags`` (JSONB on PostgreSQL): the envelope's ``properties`` **unchanged**. They are already the closed allowlist of the event
  type, so a new property never needs a schema change, and the dimensions of the briefing (``office``, ``programme_id``,
  ``product_id``, ``product_category``, ``currency``...) are searched inside it with the GIN index.

Nothing in the application updates or deletes a row.
"""

from datetime import datetime

from sqlalchemy import DDL, JSON, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import DateTime, Field, SQLModel


class TelemetryEventRow(SQLModel, table=True):
    __tablename__ = "telemetry_events"

    event_id: str = Field(primary_key=True, max_length=36)
    event_type: str = Field(index=True, max_length=64)
    timestamp: datetime = Field(index=True, sa_type=DateTime(timezone=True))  # when it happened (UTC), not when it arrived
    service: str = Field(max_length=16)  # the envelope's ``source``: inventory_api, api, backoffice, website or worker
    user_id: str | None = Field(default=None, max_length=64)  # HMAC pseudonym; NULL without an identified actor
    session_id: str | None = Field(default=None, max_length=36)
    environment: str = Field(max_length=16)
    tags: dict = Field(sa_type=JSON().with_variant(JSONB(), "postgresql"))  # the envelope's ``properties``, allowlist keys only


# The third index: GIN on ``tags``, for searches inside the JSONB (``tags @> '{"office": "miami"}'``). PostgreSQL only: SQLite has
# no GIN or JSONB, and there the table is just the local development fallback. docs/telemetry/telemetry_events.sql has it too.
event.listen(
    TelemetryEventRow.__table__,
    "after_create",
    DDL("CREATE INDEX IF NOT EXISTS ix_telemetry_events_tags ON telemetry_events USING GIN (tags)").execute_if(dialect="postgresql"),
)
