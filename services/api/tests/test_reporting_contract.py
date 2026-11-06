"""Phase 5: the /reporting endpoints match the BRIEFING contract and the design document, follow the API's conventions, and
stay apart from telemetry. The briefing's own JSON example is read from the file, so the briefing stays the source of truth."""

from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path
from uuid import uuid4

import pytest
from conftest import BOB, headers_for
from fastapi.testclient import TestClient
from prefect.testing.utilities import prefect_test_harness

import reporting
from data.pipelines import pipeline
from main import app
from reporting import router as reporting_router
from reporting.schemas import PipelineRunOut
from test_reporting import client, data_dir, engines  # noqa: F401  (fixtures)

REPO = Path(__file__).resolve().parents[3]
BRIEFING = next(REPO.glob("pipeline*BRIEFING*.md"), None)
DESIGN = (REPO / "data" / "pipelines" / "PIPELINE_DESIGN.md").read_text(encoding="utf-8")
ROUTES = {("GET", "/reporting/pipeline-runs/latest"), ("POST", "/reporting/pipeline-runs"), ("GET", "/reporting/weekly-office-program-performance")}

needs_briefing = pytest.mark.skipif(BRIEFING is None, reason="the pipeline BRIEFING is not in the repository")


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


def briefing_example() -> dict:
    text = BRIEFING.read_text(encoding="utf-8")
    after = text[text.index("`GET /reporting/weekly-office-program-performance`"):]
    return json.loads(re.search(r"```json\n(.*?)```", after, re.S).group(1))


def live_report(client) -> dict:
    assert client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 201
    return client.get("/reporting/weekly-office-program-performance").json()


# ---------------------------------------------------------------- the three endpoints, in their own module


def test_there_are_exactly_the_three_endpoints_of_the_briefing_under_reporting():
    openapi = app.openapi()["paths"]
    found = {(method.upper(), path) for path, item in openapi.items() if path.startswith("/reporting") for method in item}
    assert found == ROUTES


@needs_briefing
def test_the_paths_and_methods_are_the_ones_the_briefing_names():
    text = BRIEFING.read_text(encoding="utf-8")
    named = set(re.findall(r"`(GET|POST) (/reporting/[\w/-]+)`", text))
    assert named == ROUTES


def test_reporting_is_its_own_module_apart_from_telemetry():
    paths = set(app.openapi()["paths"])
    assert {"/telemetry/events", "/telemetry/report"} <= paths  # the technical side is still there
    assert not any(p.startswith("/telemetry") and "reporting" in p for p in paths)
    for source in Path(reporting.__file__).parent.glob("*.py"):
        imports = {n.module.split(".")[0] if isinstance(n, ast.ImportFrom) and n.module else a.name.split(".")[0]
                   for n in ast.walk(ast.parse(source.read_text())) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in (n.names if isinstance(n, ast.Import) else [n])}
        assert "telemetry" not in imports, f"{source.name} imports telemetry"


# ---------------------------------------------------------------- the KPI response is the briefing's contract


@needs_briefing
def test_the_kpi_response_has_exactly_the_shape_of_the_briefing_example(client):
    expected, actual = briefing_example(), live_report(client)
    assert set(actual) == set(expected) == {"week_start", "entries"}
    assert actual["entries"], "the demo week must have entries"
    for entry in actual["entries"]:
        assert set(entry) == set(expected["entries"][0])  # the same seven fields, no more, no fewer


@needs_briefing
def test_each_field_has_the_type_of_the_briefing_example(client):
    expected, actual = briefing_example()["entries"][0], live_report(client)["entries"][0]
    for name, value in expected.items():
        assert isinstance(actual[name], type(value)) or (isinstance(value, float) and isinstance(actual[name], (int, float))), name


def test_the_kpi_values_use_the_vocabulary_of_the_company(client):
    entries = live_report(client)["entries"]
    assert {e["office"] for e in entries} <= {"valencia", "miami"}
    assert {e["programme_id"] for e in entries} <= {"ventas-b2b", "liderazgo-basico", "onboarding-soporte"}
    for e in entries:  # a currency is never mixed: valencia is EUR, miami is USD
        assert e["currency"] == {"valencia": "EUR", "miami": "USD"}[e["office"]]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", live_report(client)["week_start"])


@needs_briefing
def test_the_kpi_names_are_the_ones_of_the_briefing_section_kpis():
    """The four KPIs of the briefing map to the four fields of the response."""
    text = BRIEFING.read_text(encoding="utf-8")
    for kpi in ("Costo de material por oficina/programa", "Kits entregados", "Frecuencia de escasez", "Frecuencia de variación de costo"):
        assert kpi in text
    fields = set(briefing_example()["entries"][0])
    assert {"total_material_cost", "kits_delivered_count", "shortage_events_count", "cost_variance_events_count"} <= fields


# ---------------------------------------------------------------- names match the design document


def test_every_task_and_the_flow_are_named_in_the_design_document():
    tasks = {name for name, obj in vars(pipeline).items() if type(obj).__name__ == "Task"}
    assert tasks and all(f"`{name}`" in DESIGN for name in tasks), [n for n in tasks if f"`{n}`" not in DESIGN]
    assert "weekly_office_performance_flow" in DESIGN and pipeline.weekly_office_performance_flow.name == "weekly-office-performance"


def test_the_destination_tables_are_named_in_the_design_document_as_in_the_code():
    from data.pipelines.weekly_office_performance import storage

    for table in (storage.weekly_performance, storage.pipeline_runs):
        assert f"reporting.{table.name}" in DESIGN
        assert table.schema == "reporting"


def test_the_functions_the_endpoints_import_are_the_ones_the_design_names():
    source = inspect.getsource(reporting_router)
    called = set(re.findall(r"interface\.(\w+)\(", source))
    assert called == {"get_latest_run", "run_weekly_office_performance", "get_weekly_performance"}
    assert all(f"`interface.{name}" in DESIGN or name in DESIGN for name in called)


def test_the_status_response_documented_in_the_design_has_the_fields_the_api_returns():
    blocks = re.findall(r"```json\n(.*?)```", DESIGN, re.S)
    status = next(b for b in blocks if '"prefect_flow_run_id"' in b)
    assert set(json.loads(status)) == set(PipelineRunOut.model_fields)


def test_the_kpi_response_documented_in_the_design_has_the_fields_of_the_briefing_contract():
    blocks = re.findall(r"```json\n(.*?)```", DESIGN, re.S)
    kpis = json.loads(next(b for b in blocks if '"entries"' in b))
    assert set(kpis) == {"week_start", "entries"}
    assert set(kpis["entries"][0]) == {"office", "programme_id", "total_material_cost", "kits_delivered_count",
                                       "shortage_events_count", "cost_variance_events_count", "currency"}


# ---------------------------------------------------------------- the conventions of the rest of the API


def test_the_whole_router_needs_a_session_like_inventory_and_suppliers():
    openapi = app.openapi()["paths"]
    for method, path in ROUTES:
        assert "security" in openapi[path][method.lower()], f"{method} {path} is not protected"
    from auth.dependencies import get_current_user

    assert any(d.dependency is get_current_user for d in reporting_router.router.dependencies)  # router level: a new route is protected by default


def test_without_a_session_every_route_answers_401_and_a_normal_user_cannot_trigger(client):
    anonymous = TestClient(app)
    assert anonymous.get("/reporting/pipeline-runs/latest").status_code == 401
    assert anonymous.get("/reporting/weekly-office-program-performance").status_code == 401
    assert anonymous.post("/reporting/pipeline-runs").status_code == 401
    assert client.post("/reporting/pipeline-runs", headers=headers_for(BOB)).status_code == 403  # admin only, as GET /telemetry/report


def test_errors_have_the_same_shape_as_the_rest_of_the_api(client):
    not_found = client.get("/reporting/pipeline-runs/latest")
    assert not_found.status_code == 404 and set(not_found.json()) == {"detail"}
    others = client.get(f"/users/{uuid4()}")  # another domain's 404 (a user that does not exist)
    assert others.status_code == 404 and set(others.json()) == set(not_found.json())

    bad_date = client.get("/reporting/weekly-office-program-performance", params={"week_start": "soon"})
    other_invalid = client.post("/users", json={"email": "not-an-email", "password": "x"})
    assert bad_date.status_code == other_invalid.status_code == 422
    assert set(bad_date.json()) == set(other_invalid.json())  # the API's own validation error format


def test_creating_a_run_answers_201_like_the_other_creating_routes(client):
    assert client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 201
