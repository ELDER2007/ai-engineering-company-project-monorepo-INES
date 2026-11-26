"""The telemetry event contract on the server side: validation against the approved JSON Schema and the stamping
of the fields a client cannot be trusted with.

``docs/telemetry/event-schemas.json`` (Draft 2020-12, schemaVersion 2.0.0) is the single source of truth; nothing
of it is copied here. Draft 2020-12 with ``format`` checking is mandatory: validated as draft-07 the closed payloads
(``unevaluatedProperties``) would silently accept extra keys.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import best_match

from core.config import get_telemetry_hmac_key, get_telemetry_schema_path

# Messages of these rules only name the keys involved; for every other rule the message would quote the
# offending value, which can be the very personal datum the allowlist exists to keep out, so it is never echoed.
_SAFE_MESSAGE_RULES = {"required", "additionalProperties", "unevaluatedProperties"}


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(get_telemetry_schema_path().read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = _schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@lru_cache(maxsize=1)
def _rules() -> dict[str, dict[str, str | None]]:
    """What the contract fixes per event type, read from the schema: its ``source`` when the variant pins one (`const`), and its
    ``userId`` rule, ``"null"`` (login attempts and failures never carry a user) or ``"string"`` (needs a verified session)."""
    schema = _schema()
    rules: dict[str, dict[str, str | None]] = {}
    for variant in schema["oneOf"]:
        props = variant["properties"]
        rules[props["event_type"]["const"]] = {
            "source": props.get("source", {}).get("const"),
            "user": props.get("userId", {}).get("type"),
        }
    inventory = schema["allOf"][0]  # the nine inventory events: sourced inventory_api and always with a user
    assert inventory["then"]["properties"]["source"] == {"const": "inventory_api"}
    for event_type in inventory["if"]["properties"]["event_type"]["enum"]:
        rules[event_type] = {"source": "inventory_api", "user": "string"}
    return rules


@lru_cache(maxsize=1)
def server_sourced_event_types() -> frozenset[str]:
    """Event types whose ``source`` the contract pins to a single value (``inventory_api``, ``api`` or ``backoffice``): the server sets it."""
    return frozenset(event_type for event_type, rule in _rules().items() if rule["source"] is not None)


def pseudonym(user_id: str) -> str:
    """`userId` of the contract: HMAC-SHA256 of the operational user id, in hex. Never the id itself."""
    return hmac.new(get_telemetry_hmac_key(), user_id.encode("utf-8"), hashlib.sha256).hexdigest()


def stamp(event: dict[str, Any], user_id: str | None) -> dict[str, Any]:
    """The event with the fields the server decides. The client's ``userId`` is ignored (the browser never knows the pseudonym; it
    comes from the verified session, or null without one) and an event whose type the contract pins to a source (the inventory
    events, and the ones the API decides: logins, registrations, suppliers, incidents...) gets that source whatever the browser
    declared: the backoffice only relays what the API answered, it is not the source of truth. An event whose variant says
    ``userId`` is null (a login attempt or failure) gets null even when a session exists, which a batch flushed after the login
    would otherwise stamp. The type's other fields are left alone for the schema to judge."""
    stamped = dict(event)
    rule = _rules().get(stamped.get("event_type"), {})
    stamped["userId"] = None if rule.get("user") == "null" or not user_id else pseudonym(user_id)
    if rule.get("source"):
        stamped["source"] = rule["source"]
    return stamped


def _variant_index(event_type: Any) -> int | None:
    """Position in the schema's ``oneOf`` of the variant that declares ``event_type``, or None if it is not catalogued."""
    for index, variant in enumerate(_schema()["oneOf"]):
        if variant["properties"]["event_type"].get("const") == event_type:
            return index
    return None


def problem(event: Any) -> dict[str, str] | None:
    """Why ``event`` breaks the contract as ``{"path", "rule", "detail"}``, or None when it is valid. Never quotes a value.

    A failed ``oneOf`` only says "no variant matched" at the root, which is useless to whoever has to fix the
    event, so it is replaced by the errors of the variant the event claims to be (or by a plain `event_type`
    error when it claims to be none of the catalogue).
    """
    errors = list(_validator().iter_errors(event))
    if not errors:
        return None
    event_type = event.get("event_type") if isinstance(event, dict) else None
    variant = _variant_index(event_type)
    expanded = []
    for error in errors:
        if error.validator != "oneOf":
            expanded.append(error)
        elif variant is None:
            return {"path": "/event_type", "rule": "enum", "detail": "violates 'enum'"}
        else:
            expanded.extend(sub for sub in error.context if sub.relative_schema_path[0] == variant)
    error = best_match(expanded or errors)
    path = "/" + "/".join(str(part) for part in error.absolute_path)
    rule = str(error.validator)
    detail = error.message if rule in _SAFE_MESSAGE_RULES else f"violates '{rule}'"
    return {"path": path, "rule": rule, "detail": detail}
