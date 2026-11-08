"""Telemetry receiver, still a STUB: it validates and acknowledges, it stores nothing (persistence is phase 3).

``POST /telemetry/events`` takes a batch ``{"events": [...]}`` (the backoffice never posts one event at a time),
checks every event against the approved contract (``contract.py``), stamps the server-owned fields and answers
200 with what it accepted and what it rejected, per event: a bad event must not cost the good ones of its batch.
A body that is not a batch at all (not JSON, no ``events`` list, too big, too many) is refused as a whole.

It logs how many events arrived and the type of each (that log is its only output). Contract for the real implementation (the frontend must not need a change): same URL, same request, same
response shape; the endpoint is public on purpose (the browser can flush with ``navigator.sendBeacon`` while the
page unloads, and a beacon cannot carry an ``Authorization`` header; website visitors are anonymous too). The
identity is taken from the bearer token only when there is one.

The body is read raw and parsed here whatever its ``Content-Type``: ``sendBeacon`` sends ``text/plain`` to stay a
CORS "simple" request (no preflight).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request
import re

from pydantic import BaseModel, ValidationError

from auth.security import decode_access_token
from users import service as users_service

from . import contract
from .schemas import TelemetryEvent

# The stub's whole visible output is this log (nothing is stored): how many events arrived and the type of each. The app does not
# configure the root logger, so this one carries its own INFO handler or the lines would never be shown.
logger = logging.getLogger("telemetry")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("INFO:     telemetry: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

_EVENT_TYPE = re.compile(r"^[a-z]+(?:_[a-z]+)+$")

router = APIRouter(tags=["telemetry"])

MAX_EVENTS_PER_BATCH = 100  # the browser buffer holds 100 events at most (plan, section 10)
MAX_BODY_BYTES = 256 * 1024  # and 256 KB


class RejectedEvent(BaseModel):
    index: int  # position in the batch
    event_id: str | None = None  # echoed only when it is a plain string of UUID length
    path: str
    rule: str
    detail: str


class Ack(BaseModel):
    received: int
    accepted: int
    rejected: list[RejectedEvent]


def _verified_user_id(authorization: str | None) -> str | None:
    """The operational id of the bearer token's user, or None (no token, bad token, deleted or inactive account)."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    doc = users_service.get_doc(user_id)
    return str(doc["id"]) if doc is not None and doc["is_active"] else None


def _loggable_type(event: Any) -> str:
    """The event's type for the log: only a well-formed ``entity_action`` name, never free text from the client (log injection)."""
    event_type = event.get("event_type") if isinstance(event, dict) else None
    return event_type if isinstance(event_type, str) and len(event_type) <= 64 and _EVENT_TYPE.match(event_type) else "<invalid>"


def _problem(event: Any, user_id: str | None) -> dict[str, str] | None:
    """Why an event is refused, or None. First the envelope (``TelemetryEvent``), then what depends on its type (the JSON Schema).
    Never quotes a value: only where it is wrong and which rule."""
    if not isinstance(event, dict):
        return {"path": "/", "rule": "type", "detail": "violates 'type'"}
    stamped = contract.stamp(event, user_id)
    try:
        TelemetryEvent.model_validate(stamped)
    except ValidationError as exc:
        first = exc.errors(include_input=False, include_url=False)[0]
        return {"path": "/" + "/".join(str(part) for part in first["loc"]), "rule": first["type"], "detail": f"violates '{first['type']}'"}
    return contract.problem(stamped)


def _batch(raw: bytes) -> list[Any]:
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, detail=f"A batch is at most {MAX_BODY_BYTES} bytes")
    try:
        body = json.loads(raw)
    except ValueError:
        raise HTTPException(422, detail="The body must be JSON") from None
    events = body.get("events") if isinstance(body, dict) else None
    if not isinstance(events, list):
        raise HTTPException(422, detail='The body must be {"events": [...]}')
    if len(events) > MAX_EVENTS_PER_BATCH:
        raise HTTPException(
            422, detail=f"A batch has at most {MAX_EVENTS_PER_BATCH} events"
        )
    return events


@router.post("/events", response_model=Ack)
async def receive_events(request: Request, authorization: Annotated[str | None, Header()] = None) -> Ack:
    events = _batch(await request.body())
    user_id = _verified_user_id(authorization)
    rejected: list[RejectedEvent] = []
    for index, event in enumerate(events):
        found = _problem(event, user_id)
        if found is not None:
            event_id = event.get("eventId") if isinstance(event, dict) else None
            rejected.append(
                RejectedEvent(
                    index=index,
                    event_id=event_id if isinstance(event_id, str) and len(event_id) == 36 else None,
                    **found,
                )
            )
    logger.info("received %d event(s): %s", len(events), ", ".join(_loggable_type(event) for event in events) or "-")
    if rejected:
        logger.info("rejected %d: %s", len(rejected), ", ".join(f"#{r.index} {r.path} ({r.rule})" for r in rejected))
    return Ack(received=len(events), accepted=len(events) - len(rejected), rejected=rejected)
