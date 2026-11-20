"""Final checks before delivery: the crash hook the design promises, the design document matching the code, and an end-to-end run
through the REAL telemetry receiver and the REAL ``telemetry_events`` table (SQLite by default; set PIPELINE_TEST_DATABASE_URL to a
PostgreSQL URL to run the same test there)."""

from __future__ import annotations

import copy
import json
import os
import re
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import text
from sqlmodel import Session, SQLModel

from data.pipelines import pipeline
from data.pipelines.weekly_office_performance import repository, storage
from main import app
from reporting.database import get_reporting_engine, get_telemetry_engine
from test_reporting import WEEK, run

REPO = Path(__file__).resolve().parents[3]
DESIGN = (REPO / "data" / "pipelines" / "PIPELINE_DESIGN.md").read_text(encoding="utf-8")
SCHEMA = json.loads((REPO / "docs" / "telemetry" / "event-schemas.json").read_text(encoding="utf-8"))
EXAMPLES = {e["event_type"]: e for e in SCHEMA["examples"]}


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


# ---------------------------------------------------------------- the crash hook of the design (section 4.4)


def start(target, prefect_id):
    return repository.start_run(target, flow_name="weekly-office-performance", trigger="scheduled", week_start=WEEK,
                                environment="production", prefect_flow_run_id=prefect_id)[0]


def test_the_flow_registers_the_crash_hook():
    assert pipeline.mark_run_crashed in pipeline.weekly_office_performance_flow.on_crashed_hooks


def test_a_crashed_flow_closes_its_log_row_as_crashed_at_once(engines):
    _, target = engines
    run_id = start(target, "pf-crash-1")
    pipeline._ACTIVE_TARGETS["pf-crash-1"] = target
    pipeline.mark_run_crashed(None, SimpleNamespace(id="pf-crash-1"), SimpleNamespace(message="the container was killed"))
    log = repository.get_run(target, run_id)
    assert log.state == "Crashed" and log.finished_at is not None and "the container was killed" in log.error
    assert "pf-crash-1" not in pipeline._ACTIVE_TARGETS


def test_a_crash_does_not_touch_a_run_that_already_finished(engines):
    _, target = engines
    run_id = start(target, "pf-done")
    repository.finish_run(target, run_id, state="Completed")
    pipeline._ACTIVE_TARGETS["pf-done"] = target
    pipeline.mark_run_crashed(None, SimpleNamespace(id="pf-done"), SimpleNamespace(message="late signal"))
    assert repository.get_run(target, run_id).state == "Completed"


def test_the_hook_never_raises_even_when_it_cannot_reach_the_database(monkeypatch):
    monkeypatch.setattr(pipeline.storage, "build_engine", lambda *_: (_ for _ in ()).throw(RuntimeError("no database")))
    pipeline.mark_run_crashed(None, SimpleNamespace(id="unknown"), SimpleNamespace(message="x"))  # must not raise


def test_a_normal_run_leaves_nothing_registered_for_the_hook(engines):
    run(engines)
    assert pipeline._ACTIVE_TARGETS == {}
    run(engines, week=date(2026, 1, 5))  # an empty week completes too
    assert pipeline._ACTIVE_TARGETS == {}


# ---------------------------------------------------------------- the design document matches the code


def test_every_field_of_the_log_table_is_described_in_the_design_document():
    section = DESIGN[DESIGN.index("### 5.2 Log de ejecución"): DESIGN.index("### 5.3 Recuperabilidad")]
    for column in storage.pipeline_runs.columns:
        assert f"`{column.name}`" in section, f"{column.name} is not described in section 5.2"


def test_what_the_implementation_table_says_is_done_exists_in_the_code():
    table = DESIGN[DESIGN.index("## Implementación del diseño"): DESIGN.index("## Estado Actual")]
    assert "✅" in table and "⏳" in table  # it says what is done and what is not
    for name in ("mark_run_crashed", "weekly_office_performance_flow", "extract_events", "load_weekly_performance"):
        assert hasattr(pipeline, name)
    assert re.search(r"Secret.*Pendiente|Pendiente.*Secret", table)  # the blocks are not claimed as implemented
    assert not any(hasattr(pipeline, n) for n in ("Secret", "load_block"))  # ...and indeed they are not


def test_the_source_table_mirror_has_the_columns_of_the_real_telemetry_model():
    from telemetry.models import TelemetryEventRow

    real, mirror = TelemetryEventRow.__table__, storage.telemetry_events
    assert [c.name for c in mirror.columns] == [c.name for c in real.columns]
    assert [c.nullable for c in mirror.columns] == [c.nullable for c in real.columns]
    assert [c.name for c in mirror.primary_key] == [c.name for c in real.primary_key] == ["event_id"]


# ---------------------------------------------------------------- end to end through the REAL receiver and table


@pytest.fixture()
def real_database(tmp_path):
    """The API's own telemetry_events table (created by its SQLModel models) and a reporting target."""
    from inventory.database import build_engine, get_db

    url = os.environ.get("PIPELINE_TEST_DATABASE_URL", "").strip()
    postgres = bool(url)
    engine = build_engine(url.replace("postgresql://", "postgresql+psycopg2://", 1) if postgres else f"sqlite:///{tmp_path / 'app.sqlite'}")
    SQLModel.metadata.create_all(engine)
    target = engine if postgres else storage.build_engine(f"sqlite:///{tmp_path / 'reporting.sqlite'}")

    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _session
    app.dependency_overrides[get_telemetry_engine] = lambda: engine
    app.dependency_overrides[get_reporting_engine] = lambda: target
    yield engine, target
    app.dependency_overrides.clear()
    if postgres:
        with engine.begin() as connection:
            connection.execute(text("drop schema if exists reporting cascade"))
        SQLModel.metadata.drop_all(engine)
    engine.dispose()


def event(event_type, when, environment="production", **properties):
    base = copy.deepcopy(EXAMPLES[event_type])
    base.update({"eventId": str(uuid4()), "requestId": str(uuid4()), "timestamp": when, "environment": environment,
                 "userId": None, "source": "backoffice"})  # the receiver stamps source and userId from the session
    base["properties"].update(properties)
    return base


def test_events_sent_to_the_real_receiver_end_up_in_the_report(real_database, auth_headers):
    engine, target = real_database
    client = TestClient(app, headers=auth_headers)  # a verified session: inventory events need one
    valencia = dict(office="valencia", programme_id="ventas-b2b", currency="EUR", product_category="training_kit")
    miami = dict(office="miami", programme_id="liderazgo-basico", currency="USD", product_category="certification")
    inbound = lambda day, order, minor, **o: event("inbound_order_created", f"2026-10-{day}T09:00:00Z", order_id=order,  # noqa: E731
                                                   unit_cost_minor=minor // 10, total_cost_minor=minor, quantity=10, **o)
    outbound = lambda day, order, **o: event("outbound_order_created", f"2026-10-{day}T10:00:00Z", order_id=order, quantity=3, **o)  # noqa: E731
    batch = [
        inbound(27, "in-1", 12000, **valencia), inbound(28, "in-2", 5000, **valencia), inbound(28, "in-3", 7550, **miami),
        outbound(27, "out-1", **valencia), outbound(28, "out-2", **valencia), outbound(29, "out-3", **miami),
        event("stock_threshold_triggered", "2026-10-29T10:00:00Z", order_id="out-3", quantity=3, **miami),
        event("kit_cost_variance_detected", "2026-10-28T09:00:00Z", order_id="in-2", quantity=10, **valencia),
        event("section_viewed", "2026-10-27T08:00:00Z"),  # not a business event: only a sign of life
        outbound(27, "dev-1", environment="test", **valencia),  # a test event: it must NOT reach the report
    ]
    ack = client.post("/telemetry/events", json={"events": batch}).json()
    assert ack["rejected"] == [] and ack["stored"] == len(batch)  # the real receiver accepted and stored all of them

    created = client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"})
    assert created.status_code == 201, created.text
    log = created.json()
    assert (log["state"], log["events_read"], log["window_events_total"], log["rows_written"]) == ("Completed", 8, 9, 2)

    report = client.get("/reporting/weekly-office-program-performance").json()
    got = {(e["office"], e["programme_id"]): e for e in report["entries"]}
    assert report["week_start"] == "2026-10-26" and set(got) == {("valencia", "ventas-b2b"), ("miami", "liderazgo-basico")}
    v, m = got[("valencia", "ventas-b2b")], got[("miami", "liderazgo-basico")]
    assert (v["total_material_cost"], v["kits_delivered_count"], v["shortage_events_count"], v["cost_variance_events_count"], v["currency"]) == (170.0, 2, 0, 1, "EUR")
    assert (m["total_material_cost"], m["kits_delivered_count"], m["shortage_events_count"], m["cost_variance_events_count"], m["currency"]) == (75.5, 1, 1, 0, "USD")


def test_the_pipeline_only_reads_the_real_table(real_database, auth_headers):
    engine, target = real_database
    client = TestClient(app, headers=auth_headers)
    client.post("/telemetry/events", json={"events": [event("section_viewed", "2026-10-27T08:00:00Z")]})
    def count() -> int:
        with engine.connect() as connection:  # always closed: on PostgreSQL an open connection would keep a lock and block the teardown
            return connection.execute(text("select count(*) from telemetry_events")).scalar()

    before = count()
    assert client.post("/reporting/pipeline-runs", json={"week_start": "2026-10-26"}).status_code == 201
    assert count() == before
