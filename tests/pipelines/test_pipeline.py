"""Unit tests of the TRANSFORMATION tasks of the weekly performance pipeline (``data/pipelines/pipeline.py``).

Every test checks ONE task in isolation:

* it calls the task's own function (``task.fn``), so Prefect's runtime is not involved (no server, no run);
* it feeds it events built IN MEMORY with the shape of the telemetry events of the briefing (``event_type``, ``timestamp`` and
  ``tags`` with ``office``, ``programme_id``, ``currency``, ``order_id``, ``total_cost_minor``...);
* it cannot touch a database or the network: an automatic fixture makes any attempt fail the test.

The tasks that compute the KPIs of the briefing ("KPIs a medir") are the ones tested most:

    calculate_total_material_cost    -> total_material_cost        "Costo de material por oficina/programa"
    count_kits_delivered             -> kits_delivered_count       "Kits entregados"
    count_shortage_events            -> shortage_events_count      "Frecuencia de escasez"
    count_cost_variance_events       -> cost_variance_events_count "Frecuencia de variación de costo"

Run:  python -m pytest tests/pipelines/test_pipeline.py
"""

from __future__ import annotations

import socket
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import sqlalchemy
from prefect import Task
from prefect.logging import disable_run_logger

from data.pipelines import pipeline
from data.pipelines.weekly_office_performance import storage
from data.process import weekly_performance as wp

WEEK = date(2026, 10, 26)
UTC = timezone.utc
VALENCIA_B2B = ("valencia", "ventas-b2b")
MIAMI_LEADERSHIP = ("miami", "liderazgo-basico")


# ---------------------------------------------------------------- isolation: no database, no network


@pytest.fixture(autouse=True)
def nothing_outside_memory(monkeypatch):
    """A unit test of a task must not reach a database or the network. If the task tried, the test fails."""

    def forbidden(*_args, **_kwargs):
        raise AssertionError("a unit test must not touch a database or the network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    monkeypatch.setattr(sqlalchemy, "create_engine", forbidden)
    monkeypatch.setattr(storage, "create_engine", forbidden)


def test_the_isolation_guard_really_blocks_a_database_and_the_network():
    with pytest.raises(AssertionError, match="must not touch"):
        sqlite3.connect(":memory:")
    with pytest.raises(AssertionError, match="must not touch"):
        socket.socket().connect(("127.0.0.1", 9))


# ---------------------------------------------------------------- helpers: events in the shape of the telemetry


def run(task: Task, *args, **kwargs):
    """Run the task's own function, with Prefect's run logger switched off (there is no run)."""
    with disable_run_logger():
        return task.fn(*args, **kwargs)


def telemetry_event(event_type, office="valencia", programme="ventas-b2b", order_id="o-1", **tags) -> wp.TelemetryEvent:
    """An event as ``telemetry_events`` stores it: its ``tags`` are the event's properties (the briefing's minimum fields)."""
    base = {"office": office, "programme_id": programme, "currency": wp.OFFICE_CURRENCY.get(office, "EUR"), "order_id": order_id,
            "product_id": "product-001", "product_category": "training_kit", "quantity": 1}
    return wp.TelemetryEvent(event_type, datetime(2026, 10, 27, 10, tzinfo=UTC), {**base, **tags})


def inbound(order_id, cost_minor, office="valencia", programme="ventas-b2b", **tags):
    return telemetry_event(wp.INBOUND, office, programme, order_id, total_cost_minor=cost_minor, unit_cost_minor=cost_minor, supplier_id="supplier-01", **tags)


def outbound(order_id, office="valencia", programme="ventas-b2b", **tags):
    return telemetry_event(wp.OUTBOUND, office, programme, order_id, stock_before=30, stock_after=29, **tags)


def shortage(order_id, office="valencia", programme="ventas-b2b"):
    return telemetry_event(wp.SHORTAGE, office, programme, order_id, minimum_stock=8, stock_before=9, stock_after=7)


def variance(order_id, office="valencia", programme="ventas-b2b"):
    return telemetry_event(wp.COST_VARIANCE, office, programme, order_id, variance_percent=20, threshold_percent=10)


def clean(events) -> list[wp.CleanEvent]:
    """What the validation task hands to the KPI tasks: the valid events, cleaned."""
    result = run(pipeline.validate_events, events)
    assert result.rejected == [], "the test data must be valid"
    return result.valid


# ---------------------------------------------------------------- the tasks are named after the KPIs of the briefing


def test_the_transformation_tasks_are_named_after_the_kpis_of_the_briefing():
    for name in ("calculate_total_material_cost", "count_kits_delivered", "count_shortage_events", "count_cost_variance_events"):
        task = getattr(pipeline, name)
        assert isinstance(task, Task) and "transform" in task.tags, name


# ---------------------------------------------------------------- KPI total_material_cost: calculate_total_material_cost


def test_total_material_cost_is_the_sum_of_the_inbound_orders_of_each_office_and_programme():
    events = clean([inbound("in-1", 12000), inbound("in-2", 5050), inbound("in-3", 7550, "miami", "liderazgo-basico")])
    assert run(pipeline.calculate_total_material_cost, events) == {
        VALENCIA_B2B: Decimal("170.50"),  # 120.00 + 50.50
        MIAMI_LEADERSHIP: Decimal("75.50"),
    }


def test_total_material_cost_counts_only_inbound_orders_not_deliveries_shortages_or_variances():
    events = clean([inbound("in-1", 1000), outbound("out-1"), shortage("out-1"), variance("in-1")])
    assert run(pipeline.calculate_total_material_cost, events) == {VALENCIA_B2B: Decimal("10.00")}


def test_total_material_cost_is_exact_to_the_cent_never_a_floating_point_approximation():
    events = clean([inbound("in-1", 10), inbound("in-2", 20)])  # 0.10 + 0.20 is 0.30000000000000004 with floats
    assert run(pipeline.calculate_total_material_cost, events)[VALENCIA_B2B] == Decimal("0.30")


def test_total_material_cost_keeps_each_office_in_its_own_currency_group():
    events = clean([inbound("in-1", 1000, "valencia", "ventas-b2b"), inbound("in-2", 1000, "miami", "ventas-b2b")])
    assert run(pipeline.calculate_total_material_cost, events) == {("valencia", "ventas-b2b"): Decimal("10.00"), ("miami", "ventas-b2b"): Decimal("10.00")}


def test_total_material_cost_of_no_events_is_nothing():
    assert run(pipeline.calculate_total_material_cost, []) == {}


def test_total_material_cost_does_not_change_its_input_and_gives_the_same_answer_every_time():
    events = clean([inbound("in-1", 999), inbound("in-2", 1)])
    snapshot = list(events)
    assert run(pipeline.calculate_total_material_cost, events) == run(pipeline.calculate_total_material_cost, events)
    assert events == snapshot


# ---------------------------------------------------------------- KPI kits_delivered_count: count_kits_delivered


def test_kits_delivered_is_the_number_of_delivery_orders_of_each_office_and_programme():
    events = clean([outbound("out-1"), outbound("out-2"), outbound("out-3", "miami", "liderazgo-basico")])
    assert run(pipeline.count_kits_delivered, events) == {VALENCIA_B2B: 2, MIAMI_LEADERSHIP: 1}


def test_a_delivery_order_of_many_units_is_one_kit_delivered_as_the_briefing_defines_it():
    """kits_delivered_count = "conteo de outbound_order_created": an order of 24 units counts once."""
    events = clean([outbound("out-1", quantity=24), outbound("out-2", quantity=3)])
    assert run(pipeline.count_kits_delivered, events) == {VALENCIA_B2B: 2}  # not 27


def test_kits_delivered_ignores_every_event_that_is_not_a_delivery_order():
    events = clean([inbound("in-1", 1000), shortage("out-1"), variance("in-1")])
    assert run(pipeline.count_kits_delivered, events) == {}


# ---------------------------------------------------------------- KPI shortage_events_count: count_shortage_events


def test_shortage_frequency_is_the_number_of_stock_threshold_events_per_office_and_programme():
    events = clean([shortage("out-1"), shortage("out-2"), shortage("out-3", "miami", "liderazgo-basico"), outbound("out-1")])
    assert run(pipeline.count_shortage_events, events) == {VALENCIA_B2B: 2, MIAMI_LEADERSHIP: 1}


def test_shortage_frequency_is_zero_for_a_programme_that_never_ran_short():
    assert run(pipeline.count_shortage_events, clean([outbound("out-1"), inbound("in-1", 100)])) == {}


# ---------------------------------------------------------------- KPI cost_variance_events_count: count_cost_variance_events


def test_cost_variance_frequency_is_the_number_of_abnormal_cost_events_per_office_and_programme():
    events = clean([variance("in-1"), variance("in-2"), variance("in-3", "miami", "liderazgo-basico"), inbound("in-1", 1000)])
    assert run(pipeline.count_cost_variance_events, events) == {VALENCIA_B2B: 2, MIAMI_LEADERSHIP: 1}


def test_cost_variance_frequency_ignores_ordinary_inbound_orders():
    assert run(pipeline.count_cost_variance_events, clean([inbound("in-1", 1000), inbound("in-2", 1200)])) == {}


# ---------------------------------------------------------------- a KPI value checked against the briefing, calculated by hand


def test_the_four_kpis_match_the_definitions_of_the_briefing_for_a_known_input_calculated_by_hand():
    """One week, two offices. THE EXPECTED NUMBERS ARE WORKED OUT BY HAND FROM THE BRIEFING, not by the code under test.

    Valencia, programme ventas-b2b (currency EUR):
        inbound  in-1  120.00 EUR  (12000 cents)      total_material_cost  = 120.00 + 50.50 = 170.50
        inbound  in-2   50.50 EUR  (5050 cents)       kits_delivered_count = 2 delivery orders (out-1 of 24 units, out-2 of 3)
        outbound out-1 (24 units)                     shortage_events_count        = 1 (the stock fell below its minimum at out-2)
        outbound out-2 (3 units)                      cost_variance_events_count   = 1 (the cost of in-2 rose 20 %)
        stock_threshold_triggered at out-2
        kit_cost_variance_detected at in-2
        out-2 arrives twice under two event ids: it is ONE order and must count once
    Miami, programme liderazgo-basico (currency USD):
        inbound  in-3   75.50 USD  (7550 cents)       total_material_cost = 75.50; one delivery; no shortage; no variance
        outbound out-3
    """
    raw = [
        inbound("in-1", 12000), inbound("in-2", 5050),
        outbound("out-1", quantity=24), outbound("out-2", quantity=3), outbound("out-2", quantity=3),  # out-2 twice
        shortage("out-2"), variance("in-2"),
        inbound("in-3", 7550, "miami", "liderazgo-basico"), outbound("out-3", "miami", "liderazgo-basico"),
    ]
    unique = run(pipeline.deduplicate_events, clean(raw))
    assert unique.duplicates_removed == 1

    rows = run(
        pipeline.build_weekly_kpi_rows, WEEK,
        run(pipeline.calculate_total_material_cost, unique.events), run(pipeline.count_kits_delivered, unique.events),
        run(pipeline.count_shortage_events, unique.events), run(pipeline.count_cost_variance_events, unique.events),
    )
    assert rows == [
        # office,     programme,          week, total_material_cost, kits_delivered_count, shortage_events_count, cost_variance_events_count, currency
        wp.WeeklyRow("miami", "liderazgo-basico", WEEK, Decimal("75.50"), 1, 0, 0, "USD"),
        wp.WeeklyRow("valencia", "ventas-b2b", WEEK, Decimal("170.50"), 2, 1, 1, "EUR"),
    ]


# ---------------------------------------------------------------- validate_events: defensive behaviour on invalid or malformed input


def reasons(events):
    result = run(pipeline.validate_events, events)
    return result.valid, [r.reason for r in result.rejected]


@pytest.mark.parametrize(
    "malformed, why",
    [
        (telemetry_event(wp.OUTBOUND, office=None), "missing or unknown office"),  # a null where there must be an office
        (telemetry_event(wp.OUTBOUND, office="madrid"), "missing or unknown office"),
        (telemetry_event(wp.OUTBOUND, office=7), "missing or unknown office"),  # a number where there must be a text
        (telemetry_event(wp.OUTBOUND, programme=None), "missing programme_id"),
        (telemetry_event(wp.OUTBOUND, programme="   "), "missing programme_id"),
        (telemetry_event(wp.OUTBOUND, currency=None), "missing currency"),
        (telemetry_event(wp.OUTBOUND, order_id=None), "missing order_id"),
        (telemetry_event(wp.OUTBOUND, order_id=""), "missing order_id"),
        (wp.TelemetryEvent(wp.OUTBOUND, datetime(2026, 10, 27, tzinfo=UTC), None), "missing or unknown office"),  # no tags at all
        (wp.TelemetryEvent(wp.OUTBOUND, datetime(2026, 10, 27, tzinfo=UTC), {}), "missing or unknown office"),
        (wp.TelemetryEvent(wp.OUTBOUND, datetime(2026, 10, 27, tzinfo=UTC), "not an object"), "malformed tags"),  # a string, not an object
        (wp.TelemetryEvent(wp.OUTBOUND, datetime(2026, 10, 27, tzinfo=UTC), ["office", "valencia"]), "malformed tags"),  # a list
        (wp.TelemetryEvent("section_viewed", datetime(2026, 10, 27, tzinfo=UTC), {"section": "inventory"}), "unsupported event_type"),
    ],
)
def test_validation_rejects_a_malformed_event_with_a_reason_and_never_crashes(malformed, why):
    valid, rejected = reasons([malformed])
    assert valid == [] and rejected == [why]


@pytest.mark.parametrize(
    "bad_cost",
    [None, "abc", "100", -1, 12.5, True, float("nan"), [], {}],  # null, text, numeric text, negative, fractional cents, boolean, NaN, containers
)
def test_validation_rejects_an_inbound_order_whose_cost_is_not_a_whole_non_negative_amount_of_cents(bad_cost):
    valid, rejected = reasons([telemetry_event(wp.INBOUND, total_cost_minor=bad_cost)])
    assert valid == [] and rejected == ["inbound_order_created without a valid cost"]


def test_validation_falls_back_to_unit_cost_times_quantity_when_there_is_no_total_cost():
    (event,) = clean([telemetry_event(wp.INBOUND, unit_cost_minor=250, quantity=4)])
    assert event.cost == Decimal("10.00")  # 250 cents x 4


def test_validation_keeps_the_good_events_of_a_batch_and_counts_the_bad_ones_by_reason():
    batch = [outbound("ok-1"), telemetry_event(wp.OUTBOUND, office=None), outbound("ok-2"), telemetry_event(wp.INBOUND), outbound("ok-3", programme="")]
    result = run(pipeline.validate_events, batch)
    assert [e.order_id for e in result.valid] == ["ok-1", "ok-2"]
    assert result.rejected_by_reason() == {"missing or unknown office": 1, "inbound_order_created without a valid cost": 1, "missing programme_id": 1}


def test_validation_normalises_office_and_currency_spelling_and_whitespace():
    (event,) = clean([telemetry_event(wp.OUTBOUND, office=" Valencia ", currency="eur", programme=" ventas-b2b ")])
    assert (event.office, event.currency, event.programme_id) == ("valencia", "EUR", "ventas-b2b")


def test_validation_of_no_events_is_nothing_valid_and_nothing_rejected():
    result = run(pipeline.validate_events, [])
    assert result.valid == [] and result.rejected == []


# ---------------------------------------------------------------- check_currency_consistency


def test_a_currency_that_is_not_the_offices_stops_the_run():
    with pytest.raises(wp.CurrencyMismatchError, match="miami/EUR"):
        run(pipeline.check_currency_consistency, clean([telemetry_event(wp.OUTBOUND, "miami", currency="EUR")]))


def test_every_wrong_office_currency_pair_is_named_in_the_error():
    events = clean([telemetry_event(wp.OUTBOUND, "miami", currency="EUR", order_id="a"), telemetry_event(wp.OUTBOUND, "valencia", currency="USD", order_id="b")])
    with pytest.raises(wp.CurrencyMismatchError) as error:
        run(pipeline.check_currency_consistency, events)
    assert "miami/EUR" in str(error.value) and "valencia/USD" in str(error.value)


def test_valencia_in_euros_and_miami_in_dollars_pass_the_currency_check():
    assert run(pipeline.check_currency_consistency, clean([outbound("a"), outbound("b", "miami", "liderazgo-basico")])) is None


# ---------------------------------------------------------------- deduplicate_events


def test_an_order_that_arrives_twice_is_counted_once_and_the_repeat_is_reported():
    result = run(pipeline.deduplicate_events, clean([outbound("same"), outbound("same"), outbound("other")]))
    assert [e.order_id for e in result.events] == ["same", "other"] and result.duplicates_removed == 1


def test_the_same_order_id_in_two_different_event_types_is_two_different_facts():
    result = run(pipeline.deduplicate_events, clean([outbound("o-1"), shortage("o-1")]))
    assert len(result.events) == 2 and result.duplicates_removed == 0


# ---------------------------------------------------------------- build_weekly_kpi_rows


def test_the_rows_cover_every_programme_that_has_any_kpi_event_with_zero_for_the_rest():
    rows = run(pipeline.build_weekly_kpi_rows, WEEK, {VALENCIA_B2B: Decimal("5.00")}, {MIAMI_LEADERSHIP: 3}, {}, {})
    assert rows == [
        wp.WeeklyRow("miami", "liderazgo-basico", WEEK, Decimal(0), 3, 0, 0, "USD"),
        wp.WeeklyRow("valencia", "ventas-b2b", WEEK, Decimal("5.00"), 0, 0, 0, "EUR"),
    ]


def test_the_rows_of_no_kpi_events_are_none():
    assert run(pipeline.build_weekly_kpi_rows, WEEK, {}, {}, {}, {}) == []


def test_the_rows_are_sorted_so_the_output_is_deterministic():
    kits = {("miami", "b"): 1, ("valencia", "a"): 1, ("miami", "a"): 1}
    assert [(r.office, r.programme_id) for r in run(pipeline.build_weekly_kpi_rows, WEEK, {}, kits, {}, {})] == [("miami", "a"), ("miami", "b"), ("valencia", "a")]


def test_each_row_carries_the_currency_of_its_office():
    rows = run(pipeline.build_weekly_kpi_rows, WEEK, {}, {VALENCIA_B2B: 1, MIAMI_LEADERSHIP: 1}, {}, {})
    assert {r.office: r.currency for r in rows} == {"valencia": "EUR", "miami": "USD"}


# ---------------------------------------------------------------- reconcile: the report must add up to its events


def reconcile_inputs(raw):
    unique = run(pipeline.deduplicate_events, clean(raw))
    rows = run(pipeline.build_weekly_kpi_rows, WEEK, run(pipeline.calculate_total_material_cost, unique.events),
               run(pipeline.count_kits_delivered, unique.events), run(pipeline.count_shortage_events, unique.events),
               run(pipeline.count_cost_variance_events, unique.events))
    return rows, unique


def test_a_report_that_adds_up_to_its_events_reconciles():
    rows, unique = reconcile_inputs([inbound("in-1", 1000), outbound("out-1"), shortage("out-1"), variance("in-1")])
    proof = run(pipeline.reconcile, rows, unique.events, unique.duplicates_removed, 4, 0, 4)
    assert proof["ok"] and proof["unique"] == 4


def test_a_report_that_lost_a_row_is_refused():
    rows, unique = reconcile_inputs([outbound("out-1"), outbound("out-2", "miami", "liderazgo-basico")])
    with pytest.raises(wp.ReconciliationError, match="outbound_order_created"):
        run(pipeline.reconcile, rows[:-1], unique.events, unique.duplicates_removed, 2, 0, 2)


def test_a_report_with_a_wrong_cost_is_refused():
    rows, unique = reconcile_inputs([inbound("in-1", 1000)])
    tampered = [wp.WeeklyRow(r.office, r.programme_id, r.week_start, r.total_material_cost + 1, 0, 0, 0, r.currency) for r in rows]
    with pytest.raises(wp.ReconciliationError, match="total cost"):
        run(pipeline.reconcile, tampered, unique.events, unique.duplicates_removed, 1, 0, 1)


def test_events_that_are_neither_valid_nor_rejected_make_the_report_refuse_to_publish():
    rows, unique = reconcile_inputs([outbound("out-1")])
    with pytest.raises(wp.ReconciliationError, match="events_read"):
        run(pipeline.reconcile, rows, unique.events, unique.duplicates_removed, 5, 0, 1)  # 4 events are unaccounted for
