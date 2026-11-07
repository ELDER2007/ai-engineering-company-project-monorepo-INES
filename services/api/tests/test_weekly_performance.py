"""Unit tests of the pure aggregation logic (data/process/weekly_performance.py), on the real telemetry shape."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from data.process import weekly_performance as wp

UTC = timezone.utc
_counter = iter(range(10_000))


def event(event_type, office="valencia", programme="ventas-b2b", currency=None, order_id=None, **extra):
    tags = {
        "office": office, "programme_id": programme, "currency": currency or wp.OFFICE_CURRENCY[office],
        "order_id": order_id or f"o-{next(_counter)}", **extra,
    }
    return wp.TelemetryEvent(event_type, datetime(2026, 10, 27, 10, tzinfo=UTC), tags)


def aggregate(events, week=date(2026, 10, 26)):
    result = wp.validate_events(events)
    assert result.rejected == []
    return wp.aggregate_by_office_programme(result.valid, week)


# ---------------------------------------------------------------- week window


def test_a_week_starts_on_monday_in_utc():
    week, start, end = wp.resolve_week_window(date(2026, 10, 28))  # a Wednesday
    assert week == date(2026, 10, 26)
    assert start == datetime(2026, 10, 26, tzinfo=UTC) and end == datetime(2026, 11, 2, tzinfo=UTC)


def test_without_a_week_the_last_complete_one_is_used():
    assert wp.resolve_week_window(None, today=date(2026, 11, 5))[0] == date(2026, 10, 26)
    assert wp.resolve_week_window(None, today=date(2026, 11, 2))[0] == date(2026, 10, 26)  # a Monday


def test_the_week_boundaries_are_inclusive_at_the_start_and_exclusive_at_the_end():
    _, start, end = wp.resolve_week_window(date(2026, 10, 26))
    assert start <= datetime(2026, 10, 26, 0, 0, tzinfo=UTC) < end
    assert not (start <= datetime(2026, 11, 2, 0, 0, tzinfo=UTC) < end)


# ---------------------------------------------------------------- aggregation


def test_the_four_kpis_are_computed_per_office_and_programme_and_money_leaves_in_currency_units():
    aggregation = aggregate(
        [
            event(wp.INBOUND, total_cost_minor=10025),  # 100.25 EUR
            event(wp.INBOUND, total_cost_minor=4000),
            event(wp.OUTBOUND), event(wp.OUTBOUND), event(wp.OUTBOUND),
            event(wp.SHORTAGE),
            event(wp.COST_VARIANCE), event(wp.COST_VARIANCE),
        ]
    )
    assert aggregation.rows == [
        wp.WeeklyRow("valencia", "ventas-b2b", date(2026, 10, 26), Decimal("140.25"), 3, 1, 2, "EUR")
    ]


def test_offices_and_programmes_are_never_mixed_and_keep_their_own_currency():
    rows = aggregate(
        [
            event(wp.INBOUND, "valencia", "a", total_cost_minor=1000),
            event(wp.INBOUND, "miami", "a", total_cost_minor=1000),
            event(wp.INBOUND, "miami", "b", total_cost_minor=500),
        ]
    ).rows
    assert [(r.office, r.programme_id, r.currency, r.total_material_cost) for r in rows] == [
        ("miami", "a", "USD", Decimal("10.00")),
        ("miami", "b", "USD", Decimal("5.00")),
        ("valencia", "a", "EUR", Decimal("10.00")),
    ]


def test_a_combination_with_only_non_cost_events_has_zero_cost_and_no_events_means_no_rows():
    (row,) = aggregate([event(wp.SHORTAGE)]).rows
    assert row.total_material_cost == 0 and row.shortage_events_count == 1
    assert aggregate([]).rows == []


def test_unit_cost_times_quantity_is_used_when_there_is_no_total_cost():
    (row,) = aggregate([event(wp.INBOUND, unit_cost_minor=250, quantity=4)]).rows
    assert row.total_material_cost == Decimal("10.00")


# ---------------------------------------------------------------- de-duplication (second line of defence)


def test_the_same_order_counted_twice_under_two_event_ids_counts_once():
    aggregation = aggregate(
        [
            event(wp.INBOUND, order_id="in-1", total_cost_minor=1000),
            event(wp.INBOUND, order_id="in-1", total_cost_minor=1000),  # same order, another event id
            event(wp.OUTBOUND, order_id="in-1"),  # same order id but another event type: a different fact
        ]
    )
    (row,) = aggregation.rows
    assert aggregation.duplicates_removed == 1
    assert row.total_material_cost == Decimal("10.00") and row.kits_delivered_count == 1


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "bad",
    [
        event(wp.INBOUND),  # no cost
        event(wp.INBOUND, total_cost_minor=-1),
        event(wp.INBOUND, total_cost_minor="abc"),
        event(wp.INBOUND, total_cost_minor=12.5),  # not whole minor units
        event(wp.INBOUND, total_cost_minor=True),
        event(wp.OUTBOUND, programme=""),
        event(wp.OUTBOUND, office="madrid", currency="EUR"),
        wp.TelemetryEvent(wp.OUTBOUND, datetime(2026, 10, 27, tzinfo=UTC), {"office": "miami", "programme_id": "x", "currency": "USD"}),  # no order_id
        wp.TelemetryEvent("section_viewed", datetime(2026, 10, 27, tzinfo=UTC), {}),
    ],
)
def test_incomplete_events_are_rejected_with_a_reason_and_never_raise(bad):
    result = wp.validate_events([bad])
    assert result.valid == [] and len(result.rejected) == 1 and result.rejected[0].reason


def test_rejections_are_counted_by_reason():
    result = wp.validate_events([event(wp.INBOUND), event(wp.INBOUND), event(wp.OUTBOUND, programme="")])
    assert result.rejected_by_reason() == {"inbound_order_created without a valid cost": 2, "missing programme_id": 1}


def test_a_currency_that_is_not_the_offices_fails_the_consistency_check():
    result = wp.validate_events([event(wp.OUTBOUND, "miami", currency="EUR")])
    with pytest.raises(wp.CurrencyMismatchError, match="miami/EUR"):
        wp.check_currency_consistency(result.valid)


def test_offices_and_currencies_are_normalised():
    (clean,) = wp.validate_events([event(wp.OUTBOUND, office=" Valencia ", currency="eur")]).valid
    assert (clean.office, clean.currency) == ("valencia", "EUR")


def test_naive_datetimes_are_taken_as_utc():
    assert wp.ensure_utc(datetime(2026, 10, 26)).tzinfo == UTC


# ---------------------------------------------------------------- reconciliation


def test_a_consistent_report_reconciles():
    events = [event(wp.INBOUND, total_cost_minor=1000), event(wp.OUTBOUND), event(wp.SHORTAGE)]
    result = wp.validate_events(events)
    aggregation = wp.aggregate_by_office_programme(result.valid, date(2026, 10, 26))
    proof = wp.reconcile(aggregation, events_read=3, rejected_count=0, valid_count=3)
    assert proof["ok"] and proof["unique"] == 3


def test_a_report_that_does_not_add_up_is_refused():
    result = wp.validate_events([event(wp.OUTBOUND), event(wp.OUTBOUND)])
    aggregation = wp.aggregate_by_office_programme(result.valid, date(2026, 10, 26))
    with pytest.raises(wp.ReconciliationError, match="events_read"):
        wp.reconcile(aggregation, events_read=5, rejected_count=0, valid_count=2)  # 3 events are unaccounted for
    tampered = wp.Aggregation(rows=[], events=aggregation.events, duplicates_removed=0)  # rows lost the kits
    with pytest.raises(wp.ReconciliationError, match="outbound_order_created"):
        wp.reconcile(tampered, events_read=2, rejected_count=0, valid_count=2)
