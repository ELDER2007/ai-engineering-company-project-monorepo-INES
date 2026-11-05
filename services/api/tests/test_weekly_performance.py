"""Unit tests of the pure aggregation logic (data/process/weekly_performance.py)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from data.process import weekly_performance as wp

UTC = timezone.utc


def event(event_type, office="valencia", programme="b2b-sales", currency=None, **extra):
    currency = currency or wp.OFFICE_CURRENCY[office]
    props = {"office": office, "programme_id": programme, "currency": currency, **extra}
    return wp.TelemetryEvent(event_type, datetime(2026, 10, 27, 10, tzinfo=UTC), props)


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
    # on a Monday, the week that just ended
    assert wp.resolve_week_window(None, today=date(2026, 11, 2))[0] == date(2026, 10, 26)


# ---------------------------------------------------------------- aggregation


def test_the_four_kpis_are_computed_per_office_and_programme():
    rows = aggregate(
        [
            event(wp.INBOUND, total_cost=100.25),
            event(wp.INBOUND, total_cost="40"),
            event(wp.OUTBOUND),
            event(wp.OUTBOUND),
            event(wp.OUTBOUND),
            event(wp.SHORTAGE),
            event(wp.COST_VARIANCE),
            event(wp.COST_VARIANCE),
        ]
    )
    assert rows == [
        wp.WeeklyRow("valencia", "b2b-sales", date(2026, 10, 26), Decimal("140.25"), 3, 1, 2, "EUR")
    ]


def test_offices_and_programmes_are_never_mixed_and_keep_their_own_currency():
    rows = aggregate(
        [
            event(wp.INBOUND, "valencia", "a", total_cost=10),
            event(wp.INBOUND, "miami", "a", total_cost=10),
            event(wp.INBOUND, "miami", "b", total_cost=5),
        ]
    )
    assert [(r.office, r.programme_id, r.currency, r.total_material_cost) for r in rows] == [
        ("miami", "a", "USD", 10),
        ("miami", "b", "USD", 5),
        ("valencia", "a", "EUR", 10),
    ]


def test_a_combination_with_only_non_cost_events_has_zero_cost():
    (row,) = aggregate([event(wp.SHORTAGE)])
    assert row.total_material_cost == 0 and row.shortage_events_count == 1


def test_no_events_means_no_rows():
    assert aggregate([]) == []


def test_unit_cost_times_quantity_is_used_when_there_is_no_total_cost():
    (row,) = aggregate([event(wp.INBOUND, unit_cost="2.5", quantity=4)])
    assert row.total_material_cost == Decimal("10.0")


# ---------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "bad",
    [
        event(wp.INBOUND),  # no cost
        event(wp.INBOUND, total_cost=-1),
        event(wp.INBOUND, total_cost="abc"),
        event(wp.INBOUND, total_cost=True),
        event(wp.OUTBOUND, programme=""),
        event(wp.OUTBOUND, office="madrid", currency="EUR"),
        wp.TelemetryEvent(wp.OUTBOUND, datetime(2026, 10, 27, tzinfo=UTC), {"office": "miami", "programme_id": "x"}),
        wp.TelemetryEvent("something_else", datetime(2026, 10, 27, tzinfo=UTC), {}),
    ],
)
def test_incomplete_events_are_rejected_with_a_reason_and_never_raise(bad):
    result = wp.validate_events([bad])
    assert result.valid == [] and len(result.rejected) == 1 and result.rejected[0].reason


def test_a_currency_that_is_not_the_offices_fails_the_consistency_check():
    result = wp.validate_events([event(wp.OUTBOUND, "miami", currency="EUR")])
    with pytest.raises(wp.CurrencyMismatchError, match="miami/EUR"):
        wp.check_currency_consistency(result.valid)


def test_offices_and_currencies_are_normalised():
    (clean,) = wp.validate_events([event(wp.OUTBOUND, office=" Valencia ", currency="eur")]).valid
    assert (clean.office, clean.currency) == ("valencia", "EUR")


def test_naive_datetimes_are_taken_as_utc():
    assert wp.ensure_utc(datetime(2026, 10, 26)).tzinfo == UTC
