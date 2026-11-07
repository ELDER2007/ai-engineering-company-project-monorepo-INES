"""The subflows of the weekly performance pipeline, one by one.

Each phase is a flow of its own with explicit inputs and outputs, so each one can be run and tested ALONE, without the
others and without the main flow. The KPI names are the ones of the briefing ("KPIs a medir"): ``total_material_cost``,
``kits_delivered_count``, ``shortage_events_count`` and ``cost_variance_events_count``."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from data.pipelines import pipeline
from data.pipelines.weekly_office_performance import repository, storage
from data.process import weekly_performance as wp

WEEK = date(2026, 10, 26)
UTC = timezone.utc


def window():
    return wp.resolve_week_window(WEEK)


def event(event_type, office="valencia", programme="ventas-b2b", order_id="o-1", **tags):
    base = {"office": office, "programme_id": programme, "currency": wp.OFFICE_CURRENCY[office], "order_id": order_id}
    return wp.TelemetryEvent(event_type, datetime(2026, 10, 27, 10, tzinfo=UTC), {**base, **tags})


def table(target):
    with target.connect() as connection:
        return connection.execute(select(storage.weekly_performance)).mappings().all()


# ---------------------------------------------------------------- phase 1: extract_kpi_events_subflow


def test_the_extraction_subflow_returns_the_events_of_the_four_kpis_and_how_many(engines):
    source, _ = engines
    _, start, end = window()
    result = pipeline.extract_kpi_events_subflow(source, start, end, "production", True)
    assert isinstance(result, pipeline.ExtractionResult)
    assert result.events_read == len(result.events) == 17
    assert {e.event_type for e in result.events} == set(wp.EVENT_TYPES)  # the four KPI events, nothing else


def test_the_extraction_subflow_reads_only_the_environment_it_is_given(engines):
    source, _ = engines
    _, start, end = window()
    assert pipeline.extract_kpi_events_subflow(source, start, end, "development", True).events_read == 0


def test_the_extraction_subflow_reads_only_the_window_it_is_given(engines):
    source, _ = engines
    _, start, end = wp.resolve_week_window(date(2025, 1, 6))  # a week with no events
    assert pipeline.extract_kpi_events_subflow(source, start, end, "production", True).events == []


def test_the_extraction_subflow_never_writes_anywhere(engines):
    source, target = engines
    _, start, end = window()
    pipeline.extract_kpi_events_subflow(source, start, end, "production", True)
    assert table(target) == []  # standalone, it loaded nothing


# ---------------------------------------------------------------- phase 2: transform_weekly_kpis_subflow


def test_the_transformation_subflow_computes_the_four_kpis_from_events_alone_without_any_database():
    events = [
        event(wp.INBOUND, order_id="in-1", total_cost_minor=12000),  # total_material_cost: 120.00 + 50.50
        event(wp.INBOUND, order_id="in-2", total_cost_minor=5050),
        event(wp.OUTBOUND, order_id="out-1"),  # kits_delivered_count: one per delivery order
        event(wp.OUTBOUND, order_id="out-2"),
        event(wp.SHORTAGE, order_id="out-2"),  # shortage_events_count
        event(wp.COST_VARIANCE, order_id="in-2"),  # cost_variance_events_count
    ]
    result = pipeline.transform_weekly_kpis_subflow(events, WEEK, True)
    assert isinstance(result, pipeline.TransformationResult)
    (row,) = result.rows
    assert (row.office, row.programme_id, row.currency, row.week_start) == ("valencia", "ventas-b2b", "EUR", WEEK)
    assert row.total_material_cost == Decimal("170.50")
    assert (row.kits_delivered_count, row.shortage_events_count, row.cost_variance_events_count) == (2, 1, 1)
    assert result.reconciliation["ok"] and result.valid_count == 6 and result.rejected_count == 0


def test_the_transformation_subflow_reports_its_kpis_with_the_names_of_the_briefing():
    (kpi,) = pipeline.transform_weekly_kpis_subflow([event(wp.OUTBOUND)], WEEK, True).kpis()
    assert set(kpi) == {"office", "programme_id", "currency", "total_material_cost", "kits_delivered_count",
                        "shortage_events_count", "cost_variance_events_count"}


def test_the_transformation_subflow_keeps_euros_and_dollars_in_separate_rows():
    events = [event(wp.INBOUND, "valencia", order_id="a", total_cost_minor=1000), event(wp.INBOUND, "miami", order_id="b", total_cost_minor=1000)]
    rows = pipeline.transform_weekly_kpis_subflow(events, WEEK, True).rows
    assert sorted((r.office, r.currency, r.total_material_cost) for r in rows) == [("miami", "USD", Decimal("10.00")), ("valencia", "EUR", Decimal("10.00"))]


def test_the_transformation_subflow_counts_what_it_rejects_and_says_why():
    events = [event(wp.OUTBOUND, order_id="ok"), event(wp.INBOUND, order_id="no-cost"), event(wp.OUTBOUND, programme="", order_id="no-programme")]
    result = pipeline.transform_weekly_kpis_subflow(events, WEEK, True)
    assert result.rejected_count == 2 and result.valid_count == 1
    assert result.rejected_by_reason == {"inbound_order_created without a valid cost": 1, "missing programme_id": 1}


def test_the_transformation_subflow_counts_a_duplicated_order_once():
    events = [event(wp.OUTBOUND, order_id="same"), event(wp.OUTBOUND, order_id="same")]
    (row,) = pipeline.transform_weekly_kpis_subflow(events, WEEK, True).rows
    assert row.kits_delivered_count == 1


def test_a_currency_that_is_not_the_offices_stops_the_transformation_subflow():
    with pytest.raises(wp.CurrencyMismatchError, match="miami/EUR"):
        pipeline.transform_weekly_kpis_subflow([event(wp.OUTBOUND, "miami", currency="EUR")], WEEK, True)


def test_the_transformation_subflow_gives_the_same_result_every_time_it_is_run():
    events = [event(wp.INBOUND, order_id="in-1", total_cost_minor=999), event(wp.OUTBOUND, order_id="out-1")]
    first = pipeline.transform_weekly_kpis_subflow(events, WEEK, True)
    assert pipeline.transform_weekly_kpis_subflow(list(reversed(events)), WEEK, True).rows == first.rows


# ---------------------------------------------------------------- phase 3: load_weekly_office_program_performance_subflow


def rows_for(cost="10.00", kits=1):
    return [wp.WeeklyRow("valencia", "ventas-b2b", WEEK, Decimal(cost), kits, 0, 0, "EUR")]


def test_the_load_subflow_writes_the_destination_table_and_says_how_many_rows(engines):
    _, target = engines
    result = pipeline.load_weekly_office_program_performance_subflow(target, rows_for(), WEEK)
    assert (result.written, result.changed, result.deleted) == (1, 0, 0)
    (row,) = table(target)
    assert (row["office"], row["programme_id"], row["week_start"], row["currency"]) == ("valencia", "ventas-b2b", WEEK, "EUR")
    assert (Decimal(row["total_material_cost"]), row["kits_delivered_count"]) == (Decimal("10.00"), 1)


def test_loading_twice_leaves_the_table_identical_and_reports_no_change(engines):
    _, target = engines
    pipeline.load_weekly_office_program_performance_subflow(target, rows_for(), WEEK)
    before = [dict(r) for r in table(target)]
    again = pipeline.load_weekly_office_program_performance_subflow(target, rows_for(), WEEK)
    assert again.changed == 0 and [dict(r) for r in table(target)] == before  # id and computed_at included


def test_loading_a_changed_value_replaces_it_and_never_adds_to_it(engines):
    _, target = engines
    pipeline.load_weekly_office_program_performance_subflow(target, rows_for("10.00", 1), WEEK)
    result = pipeline.load_weekly_office_program_performance_subflow(target, rows_for("25.00", 4), WEEK)
    (row,) = table(target)
    assert result.changed == 1 and (Decimal(row["total_material_cost"]), row["kits_delivered_count"]) == (Decimal("25.00"), 4)


def test_loading_a_week_without_that_combination_removes_it(engines):
    _, target = engines
    pipeline.load_weekly_office_program_performance_subflow(target, rows_for(), WEEK)
    result = pipeline.load_weekly_office_program_performance_subflow(target, [], WEEK)
    assert result.deleted == 1 and table(target) == []


def test_a_failure_in_the_load_subflow_leaves_the_table_as_it_was(engines, monkeypatch):
    _, target = engines
    pipeline.load_weekly_office_program_performance_subflow(target, rows_for("10.00", 1), WEEK)
    before = [dict(r) for r in table(target)]
    monkeypatch.setattr(repository, "_verify_load", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("connection lost")))
    with pytest.raises(RuntimeError, match="connection lost"):
        pipeline.load_weekly_office_program_performance_subflow(target, rows_for("99.00", 9), WEEK)
    assert [dict(r) for r in table(target)] == before


# ---------------------------------------------------------------- the optional subflows, alone


def test_the_liveness_subflow_counts_every_event_of_the_window_not_only_the_kpi_ones(engines):
    source, _ = engines
    _, start, end = window()
    assert pipeline.window_liveness_count_subflow(source, start, end, "production") == 18  # 17 KPI events + 1 navigation event


def test_the_snapshot_subflow_writes_the_events_to_data_raw_and_returns_the_path(engines, data_dir):
    source, _ = engines
    _, start, end = window()
    events = pipeline.extract_kpi_events_subflow(source, start, end, "production", True).events
    path = pipeline.raw_events_snapshot_subflow(events, WEEK, "production")
    assert path == str(data_dir / "raw" / f"weekly_events_{WEEK}_production.jsonl")
    assert len(open(path, encoding="utf-8").read().splitlines()) == 17


def test_the_report_subflow_writes_the_validation_report_to_data_eval(data_dir):
    path = pipeline.validation_report_subflow({"run_id": "abcdef0123456789", "week_start": WEEK, "state": "Completed", "kpis": []})
    assert path.startswith(str(data_dir / "eval")) and json.loads(open(path, encoding="utf-8").read())["state"] == "Completed"


# ---------------------------------------------------------------- the main flow coordinates them


def run_main(engines, **kwargs):
    source, target = engines
    kwargs.setdefault("refresh", True)
    return pipeline.weekly_office_performance_flow(week_start=WEEK, source_engine=source, target_engine=target, **kwargs)


def test_the_main_flow_gives_exactly_what_the_three_phases_give_when_run_one_after_another(engines, tmp_path):
    """Coordinating the subflows adds nothing and loses nothing: running them by hand gives the same table."""
    source, target = engines
    _, start, end = window()
    by_hand = storage.build_engine(f"sqlite:///{tmp_path / 'by-hand.sqlite'}")
    storage.create_reporting_schema(by_hand)
    extraction = pipeline.extract_kpi_events_subflow(source, start, end, "production", True)
    transformation = pipeline.transform_weekly_kpis_subflow(extraction.events, WEEK, True)
    pipeline.load_weekly_office_program_performance_subflow(by_hand, transformation.rows, WEEK)

    assert run_main(engines).state == "Completed"
    key = lambda r: {k: v for k, v in dict(r).items() if k not in ("id", "computed_at")}  # noqa: E731
    assert [key(r) for r in table(target)] == [key(r) for r in table(by_hand)]
    by_hand.dispose()


def test_a_failing_optional_subflow_is_a_warning_and_the_run_still_completes(engines, monkeypatch):
    monkeypatch.setattr(repository, "count_window_events", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("count timed out")))
    assert run_main(engines).state == "Completed"
    log = repository.get_latest_run(engines[1])
    assert log.state == "Completed" and log.window_events_total is None and "count timed out" in log.warnings
    assert len(table(engines[1])) == 5  # the report itself is complete


def test_a_failing_critical_subflow_stops_the_run_and_the_phases_after_it_never_start(engines, monkeypatch):
    loads = []
    monkeypatch.setattr(repository, "extract", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("database unreachable")))
    monkeypatch.setattr(repository, "load_week", lambda *a, **k: loads.append(1))
    with pytest.raises(ConnectionError, match="database unreachable"):
        run_main(engines)
    assert loads == []  # the load subflow was never reached
    assert repository.get_latest_run(engines[1]).state == "Failed"
