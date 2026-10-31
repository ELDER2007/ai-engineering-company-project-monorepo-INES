"""Telemetry receiver: validates the events and STORES them (``store.py``, table ``telemetry_events``), then acknowledges.

``POST /telemetry/events`` takes a batch ``{"events": [...]}`` (the backoffice never posts one event at a time),
checks every event against the approved contract (``contract.py``), stamps the server-owned fields and answers
200 with what it accepted, stored and rejected, per event: a bad event must not cost the good ones of its batch.
A body that is not a batch at all (not JSON, no ``events`` list, too big, too many) is refused as a whole.

The acknowledgement is sent only after the valid events are stored, and an ``eventId`` already stored is not an error (the
frontend retries a batch with the same ids): a retry is acknowledged as accepted and stored once. If the database fails the answer is
503, so the client retries the same batch instead of dropping it. It also logs how many events arrived and the type of each. The
contract the frontend relies on has not changed since the stub: same URL, same request, same response shape; the endpoint is public on purpose (the browser can flush with ``navigator.sendBeacon`` while the
page unloads, and a beacon cannot carry an ``Authorization`` header; website visitors are anonymous too). The
identity is taken from the bearer token only when there is one.

The body is read raw and parsed here whatever its ``Content-Type``: ``sendBeacon`` sends ``text/plain`` to stay a
CORS "simple" request (no preflight).
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
import re

from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from auth.security import decode_access_token
from inventory.database import get_db
from users import service as users_service

from . import contract, store
from .schemas import TelemetryEvent

# How many events arrived and the type of each. The app does not configure the root logger, so this one carries its own INFO
# handler or the lines would never be shown.
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
    received: int  # events in the batch
    accepted: int  # events that passed the contract (a retried event counts: it is valid)
    stored: int  # rows really written; accepted minus stored = events already stored by an earlier delivery
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


def _check(event: Any, user_id: str | None) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    """``(stamped event, None)`` when the event is valid, ``(None, why)`` when it is refused. First the envelope
    (``TelemetryEvent``), then what depends on its type (the JSON Schema). The reason never quotes a value: only where it is
    wrong and which rule. The stamped event is what gets stored: the server-owned fields are the server's, not the client's."""
    if not isinstance(event, dict):
        return None, {"path": "/", "rule": "type", "detail": "violates 'type'"}
    stamped = contract.stamp(event, user_id)
    try:
        model = TelemetryEvent.model_validate(stamped)
    except ValidationError as exc:
        first = exc.errors(include_input=False, include_url=False)[0]
        return None, {"path": "/" + "/".join(str(part) for part in first["loc"]), "rule": first["type"], "detail": f"violates '{first['type']}'"}
    found = contract.problem(stamped)
    return (None, found) if found else (model.model_dump(mode="json"), None)


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
async def receive_events(
    request: Request, session: Annotated[Session, Depends(get_db)], authorization: Annotated[str | None, Header()] = None
) -> Ack:
    events = _batch(await request.body())
    user_id = _verified_user_id(authorization)
    rejected: list[RejectedEvent] = []
    valid: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        stamped, found = _check(event, user_id)
        if stamped is not None:
            valid.append(stamped)
        else:
            event_id = event.get("eventId") if isinstance(event, dict) else None
            rejected.append(
                RejectedEvent(
                    index=index,
                    event_id=event_id if isinstance(event_id, str) and len(event_id) == 36 else None,
                    **found,
                )
            )
    try:
        stored = await run_in_threadpool(store.save, session, valid)  # sync SQL: keep it off the event loop, like routers/inventory.py
    except SQLAlchemyError:
        logger.exception("could not store %d valid event(s) of a batch of %d", len(valid), len(events))
        raise HTTPException(503, detail="The events could not be stored; retry the same batch") from None
    logger.info("received %d event(s): %s", len(events), ", ".join(_loggable_type(event) for event in events) or "-")
    if rejected:
        logger.info("rejected %d: %s", len(rejected), ", ".join(f"#{r.index} {r.path} ({r.rule})" for r in rejected))
    return Ack(received=len(events), accepted=len(valid), stored=stored, rejected=rejected)
