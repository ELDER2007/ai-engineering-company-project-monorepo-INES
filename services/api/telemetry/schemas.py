"""The envelope of a telemetry event as a Pydantic model: the shape every event has, whatever its type.

Defined for good in the stub so phase 3 (validation + persistence in Supabase) reuses it unchanged: ``model_dump(mode="json")`` is
the row to store. It mirrors the closed envelope of ``docs/telemetry/event-schemas.json`` (schemaVersion 2.0.0 and 2.1.0), the single source of
truth; what depends on the event type (the ``properties`` of each of the 40 variants, the source each one may have, which ones need a
user) is checked against that JSON Schema by ``contract.py``, not duplicated here.

Every field is required, as in the contract: ``userId`` and ``sessionId`` may be ``null`` but never absent, and an unknown key is
refused. The names are the contract's own (camelCase plus ``event_type``), not renamed to Python style, so a stored event and a
received one have the same keys.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import UUID4, AwareDatetime, BaseModel, ConfigDict, Field

SCHEMA_VERSIONS = ("2.0.0", "2.1.0")  # 2.1.0 only adds web_vital_reported; 2.0.0 events stay valid


class TelemetryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventId: UUID4  # stable id of the logical event, reused on delivery retries: the key to deduplicate by
    event_type: str = Field(pattern=r"^[a-z]+(?:_[a-z]+)+$")  # entity_action; the catalogue (40 names) is enforced by the JSON Schema
    schemaVersion: Literal["2.0.0", "2.1.0"]  # the contract version, not the app release
    timestamp: AwareDatetime  # when it happened (UTC, ends in Z: the JSON Schema checks the spelling), not when it was delivered
    userId: str | None = Field(pattern=r"^[a-f0-9]{64}$")  # HMAC pseudonym stamped by the server; null without an identified actor
    sessionId: UUID4 | None  # analytic session, never a JWT; null for direct API calls and internal jobs
    requestId: UUID4  # the operation that caused it, shared by the events of one request
    environment: Literal["development", "test", "staging", "production"]
    source: Literal["inventory_api", "api", "backoffice", "website", "worker"]
    properties: dict[str, Any]  # event-specific and closed per event_type: validated against the JSON Schema


class TelemetryBatch(BaseModel):
    """What the clients post: ``{"events": [...]}``. Used by the real endpoint of phase 3; the stub validates event by event
    (``TelemetryEvent`` + the JSON Schema) so one bad event does not cost the rest of its batch."""

    events: list[TelemetryEvent]
