"""Serialization contract, checked on the OpenAPI document the app publishes.

Guards the audit in docs/serialization-audit.md: every endpoint declares what it answers,
no response schema can carry a secret or a storage key, and every write body is strict.
"""

from __future__ import annotations

import pytest

from main import app
from suppliers.router import router as suppliers_router

SCHEMA = app.openapi()
OPERATIONS = [
    (method.upper(), path, operation)
    for path, item in SCHEMA["paths"].items()
    for method, operation in item.items()
]

# Answers that are not JSON models on purpose, each with its own explicit contract.
NO_BODY = {"DELETE"}  # 204
FILE_DOWNLOADS = {("GET", "/api/incidents/results/export")}  # text/csv, declared in the route

# Names that must never be a property of any response schema.
FORBIDDEN_IN_RESPONSES = {"hashed_password", "password", "current_password", "token_hash"}


def _success(operation: dict) -> tuple[str, dict]:
    code = next(code for code in operation["responses"] if code.startswith("2"))
    return code, operation["responses"][code]


def _ref_name(content: dict) -> str | None:
    schema = content.get("application/json", {}).get("schema", {})
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    items = schema.get("items", {})
    return items["$ref"].rsplit("/", 1)[-1] if "$ref" in items else None


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS, ids=[f"{m} {p}" for m, p, _ in OPERATIONS])
def test_every_endpoint_declares_a_response_contract(method, path, operation):
    code, response = _success(operation)
    content = response.get("content", {})
    if method in NO_BODY:
        assert code == "204" and not content
    elif (method, path) in FILE_DOWNLOADS:
        assert "text/csv" in content
    elif path.endswith("/login"):
        assert _ref_name(content) == "Token"
    else:
        assert _ref_name(content), f"{method} {path} answers with an undefined shape"


def test_the_hidden_suppliers_alias_is_as_strict_as_the_documented_mount():
    """/api/suppliers is not in OpenAPI (include_in_schema=False) but is what the backoffice calls:
    it shares this router, so every route here must name its response model or answer 204."""
    for route in suppliers_router.routes:
        assert route.response_model is not None or route.status_code == 204, route.path


def _reachable_properties(schema_name: str, seen: set[str] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    if schema_name in seen:
        return set()
    seen.add(schema_name)
    found: set[str] = set()
    schema = SCHEMA["components"]["schemas"][schema_name]
    for name, prop in schema.get("properties", {}).items():
        found.add(name)
        for ref in _refs(prop):
            found |= _reachable_properties(ref, seen)
    for ref in _refs(schema):
        if ref != schema_name:
            found |= _reachable_properties(ref, seen)
    return found


def _refs(node) -> list[str]:
    if isinstance(node, dict):
        own = [node["$ref"].rsplit("/", 1)[-1]] if "$ref" in node else []
        return own + [ref for value in node.values() for ref in _refs(value)]
    if isinstance(node, list):
        return [ref for value in node for ref in _refs(value)]
    return []


@pytest.mark.parametrize(("method", "path", "operation"), OPERATIONS, ids=[f"{m} {p}" for m, p, _ in OPERATIONS])
def test_no_response_can_carry_a_secret_or_a_storage_key(method, path, operation):
    name = _ref_name(_success(operation)[1].get("content", {}))
    if name is None:
        return
    properties = _reachable_properties(name)
    assert not properties & FORBIDDEN_IN_RESPONSES
    if path.startswith("/profiles"):
        assert "id" not in properties  # the profile's own storage id stays internal


def test_the_profile_embedded_in_the_session_has_no_storage_ids():
    assert set(SCHEMA["components"]["schemas"]["ProfileMe"]["properties"]) == {"name", "contact_email", "phone", "address"}


WRITE_BODIES = sorted(
    name
    for name in SCHEMA["components"]["schemas"]
    if name.endswith(("Create", "Update", "Change")) and not name.startswith("Body_")
)


@pytest.mark.parametrize("name", WRITE_BODIES)
def test_every_write_body_rejects_unknown_fields(name):
    assert SCHEMA["components"]["schemas"][name].get("additionalProperties") is False


def test_write_bodies_were_found():
    assert {"UserCreate", "AssetCreate", "AssetEntryCreate", "AssetExitCreate", "IncidentCreate"} <= set(WRITE_BODIES)


def test_unauthenticated_auth_flows_never_send_the_email_back():
    """Sign-up and login take the email in the request; their answers carry a message / a token only.
    (``GET /auth/me`` is authenticated and may return the caller's own email.)"""
    schemas = SCHEMA["components"]["schemas"]
    assert set(schemas["SignUpOut"]["properties"]) == {"message"}
    assert set(schemas["Token"]["properties"]) == {"access_token", "token_type", "expires_in"}
    for name in ("SignUpOut", "Token"):
        assert not _reachable_properties(name) & {"email", "contact_email", "password", "hashed_password"}


def test_the_list_row_of_incidents_is_lighter_than_its_detail():
    schemas = SCHEMA["components"]["schemas"]
    row, detail = set(schemas["IncidentListItem"]["properties"]), set(schemas["IncidentOut"]["properties"])
    assert row < detail
    assert {"description", "customer_email", "history"} & row == set()


def test_health_has_a_declared_shape():
    from fastapi.testclient import TestClient

    assert TestClient(app).get("/health").json() == {"status": "ok"}  # no lifespan: no databases touched
    assert "HealthOut" in SCHEMA["components"]["schemas"]


def test_every_route_decorator_states_its_response_model():
    """The decorator itself says what the route answers: a model, or ``response_model=None`` for the
    routes with no JSON body (204 and the CSV file). Reads the source, so a new route cannot skip it."""
    import re
    from pathlib import Path

    api = Path(__file__).resolve().parents[1]
    decorator = re.compile(r"@(?:router|public_router|app)\.(?:get|post|put|patch|delete)\((.*?)\)\n(?:async )?def (\w+)", re.S)
    missing = []
    for path in ("main.py", "auth/router.py", "users/router.py", "profiles/router.py", "suppliers/router.py",
                 "incidents/router.py", "incidents/incident_router.py", "routers/inventory.py"):
        for args, name in decorator.findall((api / path).read_text()):
            if "response_model" not in args:
                missing.append(f"{path}:{name}")
    assert missing == []
