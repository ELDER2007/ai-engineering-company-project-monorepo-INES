"""Technical analysis pipeline: each metric loads its events from the table, transforms them with Pandas and returns a JSON-ready list of dicts."""

from __future__ import annotations

import ast
import inspect
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlmodel import Session, func, select

from telemetry import analysis
from telemetry.models import TelemetryEventRow

pytestmark = pytest.mark.usefixtures("telemetry_db")

T0 = datetime(2026, 10, 27, 10, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)


@pytest.fixture
def db(telemetry_db):
    with Session(telemetry_db) as session:
        yield session


def put(db, event_type: str, count: int = 1, when: datetime = T0, environment: str = "test", service: str = "backoffice", **tags) -> None:
    for _ in range(count):
        db.add(TelemetryEventRow(event_id=str(uuid4()), event_type=event_type, timestamp=when, service=service, environment=environment, tags=dict(tags)))
    db.commit()


# --- the rules of the pipeline ----------------------------------------------------------------------

METRIC_FUNCTIONS = [function for name, function in inspect.getmembers(analysis, inspect.isfunction) if name.startswith("analyze_")]


def test_there_are_at_least_three_metric_functions():
    assert len(METRIC_FUNCTIONS) >= 3


@pytest.mark.parametrize("function", METRIC_FUNCTIONS, ids=lambda function: function.__name__)
def test_metric_functions_compute_with_pandas_not_with_loops(function):
    tree = ast.parse(inspect.getsource(function).strip())
    loops = [type(node).__name__ for node in ast.walk(tree) if isinstance(node, (ast.For, ast.While, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp))]
    assert loops == []


@pytest.mark.parametrize("function", METRIC_FUNCTIONS, ids=lambda function: function.__name__)
def test_metric_functions_return_a_json_list_of_dicts_with_and_without_data(db, function):
    empty = function(db)  # no events: an empty list, never an error
    if function is analysis.analyze_technical_coverage:  # ...except the coverage, whose job is to list what never arrived
        assert len(empty) == len(analysis.TECHNICAL_EVENT_TYPES) and not any(row["observed"] for row in empty)
    else:
        assert empty == []
    put(db, "login_failed", 3, reason="invalid_credentials", duration_ms=40)
    put(db, "login_succeeded", 2, duration_ms=30)
    put(db, "section_load_completed", 3, section="home", duration_ms=300, outcome="error")
    put(db, "application_error_occurred", component="auth", error_code="render_failed")
    put(db, "authorization_denied", route_id="users", status_code=403)
    put(db, "session_expired", reason="token_expired")
    put(db, "web_vital_reported", metric="LCP", value=1200.5, rating="good", section="home")
    put(db, "http_request_completed", service="api", route_id="users", status_code=200, duration_ms=40)
    rows = function(db)
    assert isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows)
    json.dumps(rows, allow_nan=False)  # NaN must have become None


@pytest.mark.parametrize("function", METRIC_FUNCTIONS, ids=lambda function: function.__name__)
def test_metric_functions_are_idempotent_and_never_write(db, function):
    put(db, "login_failed", 3, reason="invalid_credentials", duration_ms=40)
    put(db, "section_load_completed", 3, section="home", duration_ms=300, outcome="error")
    put(db, "application_error_occurred", component="auth", error_code="render_failed")
    before = db.exec(select(func.count()).select_from(TelemetryEventRow)).one()
    first, second = function(db), function(db)
    assert first == second
    assert db.exec(select(func.count()).select_from(TelemetryEventRow)).one() == before and not db.new and not db.dirty and not db.deleted


def test_every_metric_row_has_a_grouping_dimension_not_a_lone_global_number(db):
    put(db, "login_failed", 1, reason="invalid_credentials", duration_ms=1)
    put(db, "section_load_completed", 1, section="home", duration_ms=1, outcome="success")
    for function in METRIC_FUNCTIONS:
        for row in function(db):
            assert len(row) >= 2, (function.__name__, row)  # a dimension plus at least one value


def test_each_metric_loads_only_the_rows_it_needs(db, monkeypatch):
    put(db, "section_viewed", 30)
    put(db, "login_failed", 2, reason="invalid_credentials", duration_ms=1)
    loaded = []
    real = analysis.load_events
    monkeypatch.setattr(analysis, "load_events", lambda *args, **kwargs: (frame := real(*args, **kwargs), loaded.append(len(frame)))[0])
    analysis.analyze_login_failures_by_reason(db)
    analysis.analyze_error_rate_by_type(db)
    assert loaded == [2, 2]  # the 30 page views were never read
    assert "tags" not in real(db, with_tags=False).columns


# --- timestamps and the period ----------------------------------------------------------------------


def test_timestamps_become_utc_datetimes_before_grouping(db):
    put(db, "section_viewed")
    events = analysis.load_events(db)
    assert str(events["timestamp"].dtype).endswith(", UTC]")
    assert events["day"].tolist() == ["2026-10-27"]


def test_days_group_by_utc_date_sort_chronologically_and_leave_no_gaps(db):
    put(db, "section_viewed", 2, when=datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc))
    put(db, "section_viewed", 1, when=datetime(2026, 10, 1, 0, 0, 0, tzinfo=timezone.utc))
    put(db, "section_viewed", 1, when=datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc))
    assert analysis.analyze_events_per_day(db) == [{"day": "2026-09-30", "events": 2}, {"day": "2026-10-01", "events": 1}, {"day": "2026-10-02", "events": 0}, {"day": "2026-10-03", "events": 1}]


def test_the_period_filters_in_sql_with_an_inclusive_start_and_an_exclusive_end(db):
    for hour in (10, 11, 12):
        put(db, "section_viewed", when=T0.replace(hour=hour))
    assert analysis.analyze_events_per_day(db, start_date=T0, end_date=T0.replace(hour=12)) == [{"day": "2026-10-27", "events": 2}]


def test_the_environment_filter(db):
    put(db, "section_viewed", environment="production")
    put(db, "section_viewed", environment="test")
    assert analysis.analyze_events_per_day(db, environment="production") == [{"day": "2026-10-27", "events": 1}]


def test_a_tag_that_shadows_a_table_column_does_not_break_the_frame(db):
    db.add(TelemetryEventRow(event_id=str(uuid4()), event_type="section_viewed", timestamp=T0, service="backoffice", environment="test", tags={"service": "hacked", "section": "home"}))
    db.commit()
    events = analysis.load_events(db)
    assert events["service"].tolist() == ["backoffice"] and events["section"].tolist() == ["home"]


def test_window_is_truncated_only_past_the_row_cap(db, monkeypatch):
    put(db, "section_viewed", 3)
    monkeypatch.setattr(analysis, "MAX_ROWS", 3)
    assert analysis.window_is_truncated(db) is False
    put(db, "section_viewed", 1)
    assert analysis.window_is_truncated(db) is True
    assert sum(row["events"] for row in analysis.analyze_events_per_day(db)) == 3  # the metrics read the oldest MAX_ROWS


# --- volume -----------------------------------------------------------------------------------------


def test_events_by_type_ranks_what_dominates_with_its_share(db):
    put(db, "section_viewed", 3)
    put(db, "login_failed", 1, reason="invalid_credentials", duration_ms=1)
    assert analysis.analyze_events_by_type(db) == [{"event_type": "section_viewed", "events": 3, "share": 0.75}, {"event_type": "login_failed", "events": 1, "share": 0.25}]


def test_events_by_source_groups_by_service_and_environment(db):
    put(db, "section_viewed", 3)
    put(db, "login_failed", 1, service="api", environment="production", reason="invalid_credentials", duration_ms=1)
    assert analysis.analyze_events_by_source(db) == [{"service": "backoffice", "environment": "test", "events": 3}, {"service": "api", "environment": "production", "events": 1}]


def test_technical_coverage_lists_every_technical_type_and_flags_the_ones_that_never_arrived(db):
    put(db, "login_failed", 2, reason="invalid_credentials", duration_ms=1)
    put(db, "section_viewed", 5)  # business type: not part of this metric
    coverage = {row["event_type"]: row for row in analysis.analyze_technical_coverage(db)}
    assert set(coverage) == set(analysis.TECHNICAL_EVENT_TYPES)
    assert coverage["login_failed"] == {"event_type": "login_failed", "events": 2, "observed": True}
    assert coverage["http_request_completed"] == {"event_type": "http_request_completed", "events": 0, "observed": False}


# --- errors -----------------------------------------------------------------------------------------


def test_errors_per_day_with_the_rate_over_the_technical_events_of_the_day(db):
    put(db, "application_error_occurred", 2, component="inventory", error_code="network_failed")
    put(db, "login_succeeded", 8, duration_ms=10)
    put(db, "login_succeeded", 5, when=T0 + DAY, duration_ms=10)
    put(db, "section_viewed", 50)  # not technical: neither numerator nor denominator
    assert analysis.analyze_errors_per_day(db) == [
        {"day": "2026-10-27", "technical_events": 10, "errors": 2, "error_rate": 0.2},
        {"day": "2026-10-28", "technical_events": 5, "errors": 0, "error_rate": 0.0},
    ]


def test_error_rate_by_type_covers_technical_failures_and_not_domain_refusals(db):
    put(db, "section_load_completed", 3, section="home", duration_ms=1, outcome="success")
    put(db, "section_load_completed", 1, section="home", duration_ms=1, outcome="error")
    put(db, "login_failed", 2, reason="invalid_credentials", duration_ms=1)  # a domain refusal, not a technical error
    put(db, "login_failed", 1, reason="internal_error", duration_ms=1)  # the server failing
    put(db, "http_request_completed", 2, service="api", route_id="users", status_code=500, duration_ms=1)
    put(db, "http_request_completed", 2, service="api", route_id="users", status_code=400, duration_ms=1)
    put(db, "section_viewed", 9)  # not technical: not listed
    assert analysis.analyze_error_rate_by_type(db) == [
        {"event_type": "http_request_completed", "events": 4, "errors": 2, "error_rate": 0.5},
        {"event_type": "login_failed", "events": 3, "errors": 1, "error_rate": 0.3333},
        {"event_type": "section_load_completed", "events": 4, "errors": 1, "error_rate": 0.25},
    ]


def test_application_errors_group_by_component_and_code(db):
    put(db, "application_error_occurred", 2, component="inventory", error_code="network_failed")
    put(db, "application_error_occurred", 1, component="auth", error_code="render_failed")
    assert analysis.analyze_application_errors(db) == [
        {"component": "inventory", "error_code": "network_failed", "errors": 2},
        {"component": "auth", "error_code": "render_failed", "errors": 1},
    ]


def test_rows_with_a_null_dimension_are_left_out_of_the_group_by(db):
    put(db, "application_error_occurred", component="auth", error_code="render_failed")
    put(db, "application_error_occurred")  # no component, no error_code
    put(db, "application_error_occurred", component=None, error_code="render_failed")
    assert analysis.analyze_application_errors(db) == [{"component": "auth", "error_code": "render_failed", "errors": 1}]


# --- access -----------------------------------------------------------------------------------------


def test_auth_failure_rate_is_failed_over_failed_plus_succeeded_per_day(db):
    put(db, "login_failed", 1, reason="invalid_credentials", duration_ms=1)
    put(db, "login_succeeded", 3, duration_ms=1)
    put(db, "login_attempted", 10)  # in flight or not, it is not an outcome: outside the denominator
    put(db, "login_failed", 2, when=T0 + DAY, reason="invalid_credentials", duration_ms=1)
    put(db, "login_failed", 1, when=T0 + 3 * DAY, reason="internal_error", duration_ms=1)
    put(db, "login_succeeded", 1, when=T0 + 3 * DAY, duration_ms=1)
    put(db, "section_viewed", 5, when=T0 + DAY)
    assert analysis.analyze_auth_failure_rate(db) == [
        {"day": "2026-10-27", "succeeded": 3, "failed": 1, "attempts": 4, "failure_rate": 0.25},
        {"day": "2026-10-28", "succeeded": 0, "failed": 2, "attempts": 2, "failure_rate": 1.0},
        {"day": "2026-10-29", "succeeded": 0, "failed": 0, "attempts": 0, "failure_rate": None},
        {"day": "2026-10-30", "succeeded": 1, "failed": 1, "attempts": 2, "failure_rate": 0.5},
    ]


def test_auth_failure_rate_with_only_one_kind_of_event_still_has_both_columns(db):
    put(db, "login_succeeded", 2, duration_ms=1)
    assert analysis.analyze_auth_failure_rate(db) == [{"day": "2026-10-27", "succeeded": 2, "failed": 0, "attempts": 2, "failure_rate": 0.0}]
    put(db, "login_failed", 1, when=T0 + DAY, reason="invalid_credentials", duration_ms=1)
    assert analysis.analyze_auth_failure_rate(db)[1] == {"day": "2026-10-28", "succeeded": 0, "failed": 1, "attempts": 1, "failure_rate": 1.0}


def test_auth_failure_rate_respects_the_period(db):
    put(db, "login_failed", 1, reason="invalid_credentials", duration_ms=1)
    assert analysis.analyze_auth_failure_rate(db, start_date=T0 + DAY) == []


def test_login_failures_by_reason_and_latency_by_outcome(db):
    put(db, "login_failed", 2, reason="invalid_credentials", duration_ms=300)
    put(db, "login_failed", 1, reason="rate_limited", duration_ms=10)
    put(db, "login_succeeded", 2, duration_ms=100)
    assert analysis.analyze_login_failures_by_reason(db) == [{"reason": "invalid_credentials", "failures": 2}, {"reason": "rate_limited", "failures": 1}]
    assert analysis.analyze_login_latency(db) == [
        {"outcome": "failed", "logins": 3, "p50_ms": 300.0, "p95_ms": 300.0},
        {"outcome": "succeeded", "logins": 2, "p50_ms": 100.0, "p95_ms": 100.0},
    ]


def test_access_denied_by_route_and_status_per_day_and_expired_sessions(db):
    put(db, "authorization_denied", 2, route_id="inventory_assets", status_code=401)
    put(db, "authorization_denied", route_id="users", status_code=403, when=T0 + DAY)
    put(db, "session_expired", reason="token_expired")
    assert analysis.analyze_access_denied(db) == [{"route_id": "inventory_assets", "status_code": 401, "denied": 2}, {"route_id": "users", "status_code": 403, "denied": 1}]
    assert analysis.analyze_access_denied_per_day(db) == [{"day": "2026-10-27", "denied": 2}, {"day": "2026-10-28", "denied": 1}]
    assert analysis.analyze_sessions_expired(db) == [{"reason": "token_expired", "sessions": 1}]


# --- latency ----------------------------------------------------------------------------------------


def test_section_load_latency_reports_percentiles_errors_and_the_target_per_section(db):
    for ms in (500, 600, 700, 5000):
        put(db, "section_load_completed", section="inventory", duration_ms=ms, outcome="success")
    put(db, "section_load_completed", section="home", duration_ms=200, outcome="error", when=T0 + DAY)
    rows = analysis.analyze_section_load_latency(db)
    by_name = {row["section"]: row for row in rows}
    assert [row["section"] for row in rows] == ["inventory", "home"]  # slowest p95 first
    assert by_name["inventory"]["max_ms"] == 5000 and by_name["inventory"]["over_target"] is True and by_name["inventory"]["p50_ms"] == 650
    assert by_name["home"]["error_rate"] == 1.0 and by_name["home"]["over_target"] is False


def test_section_load_latency_per_day_is_the_trend(db):
    for ms in (100, 300):
        put(db, "section_load_completed", section="home", duration_ms=ms, outcome="success")
    put(db, "section_load_completed", section="home", duration_ms=900, outcome="success", when=T0 + DAY)
    assert analysis.analyze_section_load_latency_per_day(db) == [
        {"day": "2026-10-27", "loads": 2, "p50_ms": 200.0, "p95_ms": 290.0},
        {"day": "2026-10-28", "loads": 1, "p50_ms": 900.0, "p95_ms": 900.0},
    ]


def test_a_non_numeric_duration_is_skipped_not_counted_as_zero(db):
    put(db, "section_load_completed", section="home", duration_ms="fast", outcome="success")
    assert analysis.analyze_section_load_latency(db)[0]["p50_ms"] is None


def test_web_vitals_give_p75_and_the_ratings_per_metric(db):
    for value, rating in ((1000, "good"), (2000, "good"), (3000, "needs-improvement"), (5000, "poor")):
        put(db, "web_vital_reported", metric="LCP", value=value, rating=rating, section="home")
    (lcp,) = analysis.analyze_web_vitals(db)
    assert lcp["metric"] == "LCP" and lcp["readings"] == 4 and lcp["p75"] == 3500 and lcp["good"] == 2 and lcp["poor"] == 1 and lcp["poor_rate"] == 0.25


def test_a_tiny_cls_is_not_rounded_to_zero(db):
    for value in (0.001, 0.003, 0.004):
        put(db, "web_vital_reported", metric="CLS", value=value, rating="good", section="home")
    assert analysis.analyze_web_vitals(db)[0]["p75"] == 0.0035


def test_http_only_counts_5xx_as_failure_and_is_empty_until_the_api_emits_it(db):
    put(db, "section_viewed")
    assert analysis.analyze_http_by_route(db) == [] and analysis.analyze_http_per_day(db) == []
    for status in (200, 400, 404, 500):
        put(db, "http_request_completed", service="api", route_id="suppliers", status_code=status, duration_ms=100)
    (route,) = analysis.analyze_http_by_route(db)
    assert route["route"] == "suppliers" and route["requests"] == 4 and route["server_errors"] == 1 and route["error_rate"] == 0.25
    assert analysis.analyze_http_per_day(db)[0]["server_errors"] == 1


# --- findings and the whole report ------------------------------------------------------------------


def codes(db, severity=None):
    return [f["code"] for f in analysis.build_report(db)["findings"] if severity in (None, f["severity"])]


def test_a_healthy_dataset_only_reports_the_instrumentation_gap(db):
    put(db, "login_succeeded", 10, duration_ms=100)
    put(db, "section_load_completed", 5, section="home", duration_ms=300, outcome="success")
    assert codes(db) == ["instrumentation_gap"]


def test_errors_are_critical_and_sorted_before_warnings_and_info(db):
    put(db, "application_error_occurred", component="auth", error_code="unhandled_exception")
    put(db, "authorization_denied", route_id="users", status_code=403)
    severities = [f["severity"] for f in analysis.build_report(db)["findings"]]
    assert severities == sorted(severities, key=["critical", "warning", "info"].index)
    assert "application_errors" in codes(db, "critical") and "authorization_denied" in codes(db, "warning")


def test_login_failure_rate_alert_needs_a_minimum_sample(db):
    put(db, "login_failed", 2, reason="invalid_credentials", duration_ms=1)
    assert "login_failure_rate" not in codes(db)  # 100 % of 2: no trend yet
    put(db, "login_failed", 2, reason="invalid_credentials", duration_ms=1)
    put(db, "login_succeeded", 2, duration_ms=1)
    assert "login_failure_rate" in codes(db)


def test_login_internal_error_is_critical_even_with_a_tiny_sample(db):
    put(db, "login_failed", reason="internal_error", duration_ms=1)
    assert "login_internal_error" in codes(db, "critical")


def test_slow_section_and_poor_web_vital_are_warnings(db):
    put(db, "section_load_completed", 3, section="orders", duration_ms=9000, outcome="success")
    put(db, "web_vital_reported", metric="INP", value=900, rating="poor", section="orders")
    assert {"slow_section", "poor_web_vital"} <= set(codes(db, "warning"))


def test_api_5xx_and_slow_routes_are_flagged_when_http_is_observed(db):
    put(db, "http_request_completed", service="api", route_id="inventory_assets", status_code=500, duration_ms=2500)
    assert {"api_5xx_rate", "api_slow_route"} <= set(codes(db))


def test_the_report_of_no_events_is_valid_and_says_what_it_cannot_see(db):
    report = analysis.build_report(db)
    assert set(report) == {"metrics", "findings", "truncated"} and report["truncated"] is False
    assert report["metrics"]["events_per_day"] == [] and report["metrics"]["auth_failure_rate"] == []
    assert [f["code"] for f in report["findings"]] == ["instrumentation_gap"]


def test_the_report_has_one_list_per_metric_and_is_json_serializable(db):
    put(db, "login_failed", reason="invalid_credentials", duration_ms=1)
    metrics = analysis.build_report(db)["metrics"]
    assert {"events_per_day", "error_rate_by_type", "auth_failure_rate"} <= set(metrics)
    assert all(isinstance(rows, list) for rows in metrics.values())
    json.dumps(analysis.build_report(db), allow_nan=False)
