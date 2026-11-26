"""Technical analysis pipeline over ``telemetry_events``: one function per operational metric.

Every ``analyze_*`` function follows the same order: load (SQL) -> refine (Pandas) -> convert types -> group -> aggregate -> return a
list of dicts, JSON-serializable (``.reset_index().to_dict(orient="records")``). Each row of that list is one group of the metric's
grouping dimension (a day, an event type, a section, a route...): there are no global numbers without context. Where each filter lives:

* SQL: the ``[start_date, end_date)`` period (start inclusive, end exclusive, UTC), the environment and ``event_type``;
* Pandas: everything inside ``tags`` (section, route, component...) and the derived flags (``is_error``) and rates.

Each function loads only the rows its metric needs (never the whole table) and applies the period once, in SQL. The period is not
decided here: the endpoint resolves it (``report.resolve_window``: by default the last 7 days) and passes it to every function. A row
whose grouping dimension is null is left out of that group-by (a ``groupby`` on a null key is meaningless); the contract validated at
ingestion (``contract.py``) already makes the dimensions of every technical event required.

Each metric function is independent and free of side effects: it only reads (one SELECT), builds its own DataFrame and returns new
data, so calling it twice with the same parameters on the same data gives the same result. Metrics are computed with Pandas operations
(``groupby``, ``agg``, ``quantile``, vectorized arithmetic), never with Python loops over rows or groups.

The ``timestamp`` is converted to a UTC datetime (``pd.to_datetime(..., utc=True)``) in ``load_events``, BEFORE any grouping: the ``day``
key every daily series is grouped on is built from that datetime, never from a string, so the groups are right and sorted
chronologically.

This is a TECHNICAL report (is the system healthy, fast and observable?), not a business one: sales, conversion and revenue belong to
the data pipelines milestone. A rate is ``None`` (not 0) when its denominator is 0, and a latency is ``None`` without samples: "no
data" must not read as "no failures". The thresholds of ``derive_findings`` are the plan's initial proposals
(docs/telemetry/telemetry-plan.md, section 12), pending a real baseline.

The endpoint never calls these per request: ``report.py`` runs ``build_report`` and caches the result.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlmodel import Session, select

from .models import TelemetryEventRow

MAX_ROWS = 50_000  # a frame is held in memory; past this ``window_is_truncated`` says so instead of exhausting the process

# Plan, section 12 and section 10: proposed thresholds, not agreed service levels.
LOGIN_FAILURE_RATE_ALERT = 0.30  # >30 % of the completed logins failed (the plan also asks for >20 failures in 5 min)
SECTION_LOAD_P95_TARGET_MS = 2000  # "objetivo inicial propuesto p95 < 2 segundos"
API_ERROR_RATE_ALERT = 0.01  # >1 % 5xx
API_P95_ALERT_MS = 1000
MIN_SAMPLE_FOR_RATE_ALERT = 5  # below this a rate is shown but never raises a finding: 1 failure of 2 is not a trend

# Technical event types of the catalogue (plan, section 10, "Salud tecnica y procesos", plus the technical ones of access and navigation).
TECHNICAL_EVENT_TYPES = (
    "http_request_completed",
    "dependency_call_completed",
    "application_error_occurred",
    "background_job_completed",
    "telemetry_delivery_failed",
    "web_vital_reported",
    "section_load_completed",
    "login_attempted",
    "login_succeeded",
    "login_failed",
    "authorization_denied",
    "session_expired",
)

_COLUMNS = ["event_type", "timestamp", "service", "environment", "tags"]


# --- load and refine --------------------------------------------------------------------------------


def _filtered(statement, event_types, start_date, end_date, environment):
    """``statement`` restricted in SQL to the event types, the ``[start_date, end_date)`` period and the environment."""
    if event_types:
        statement = statement.where(TelemetryEventRow.event_type.in_(event_types))
    if start_date is not None:
        statement = statement.where(TelemetryEventRow.timestamp >= start_date)
    if end_date is not None:
        statement = statement.where(TelemetryEventRow.timestamp < end_date)
    if environment is not None:
        statement = statement.where(TelemetryEventRow.environment == environment)
    return statement


def load_events(
    session: Session,
    event_types: tuple[str, ...] | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    environment: str | None = None,
    with_tags: bool = True,
) -> pd.DataFrame:
    """The events of the period as a DataFrame, oldest first, at most ``MAX_ROWS`` of them.

    The period, the environment and the event types are filtered in SQL; the keys of ``tags`` become columns (a key missing from an
    event is NaN) and the timestamp becomes a UTC datetime plus its ``day`` ("YYYY-MM-DD"). A tag that would shadow a real column
    (``service``...) is left out: the columns of the table win. ``with_tags=False`` does not even read the JSON column, for the
    metrics that only count events.
    """
    columns = _COLUMNS if with_tags else [name for name in _COLUMNS if name != "tags"]
    statement = _filtered(select(*(getattr(TelemetryEventRow, name) for name in columns)), event_types, start_date, end_date, environment)
    records = [tuple(record) for record in session.exec(statement.order_by(TelemetryEventRow.timestamp).limit(MAX_ROWS)).all()]
    frame = pd.DataFrame(records, columns=columns)
    # Convert BEFORE grouping. SQLite returns naive datetimes (the table holds UTC), PostgreSQL aware ones: utc=True takes both to UTC.
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["day"] = frame["timestamp"].dt.strftime("%Y-%m-%d")
    if not with_tags:
        return frame
    tags = pd.DataFrame(frame["tags"].tolist(), index=frame.index)  # ``tags`` is NOT NULL in the table
    tags = tags.drop(columns=tags.columns.intersection(frame.columns))
    return frame.drop(columns="tags").join(tags)


def window_is_truncated(session: Session, start_date=None, end_date=None, environment=None) -> bool:
    """Whether the period holds more events than ``MAX_ROWS``, i.e. whether the metrics above saw only the oldest ones. Not a metric:
    the caller reports it next to them."""
    capped = _filtered(select(TelemetryEventRow.event_id), None, start_date, end_date, environment).limit(MAX_ROWS + 1).subquery()
    return session.exec(select(func.count()).select_from(capped)).one() > MAX_ROWS


# --- small Pandas helpers (no loops) ----------------------------------------------------------------


def _dimension(frame: pd.DataFrame, name: str) -> pd.Series:
    """Column ``name`` as text; an absent tag or a null is NaN, which ``groupby`` and ``_count_series`` leave out."""
    if name not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype=object)
    return frame[name].astype(str).where(frame[name].notna())


def _number(frame: pd.DataFrame, name: str) -> pd.Series:
    """Column ``name`` as numbers; absent or non-numeric values are NaN, never 0."""
    if name not in frame:
        return pd.Series(float("nan"), index=frame.index, dtype="float64")
    return pd.to_numeric(frame[name], errors="coerce")


def _count_series(labels: pd.Series) -> pd.Series:
    """Occurrences per label (null labels are left out), largest first and by name within a tie (stable sort after sorting the names)."""
    counts = labels.dropna().astype(str).value_counts()
    return counts.sort_index().sort_values(ascending=False, kind="stable")


def _ratio(part: pd.Series, whole: pd.Series) -> pd.Series:
    """``part / whole`` to 4 decimals; NaN where ``whole`` is 0 (no denominator is not a 0 rate)."""
    return (part / whole.where(whole > 0)).round(4)


def _percentiles(frame: pd.DataFrame, by: str, column: str, **named: float) -> pd.DataFrame:
    """One row per group of ``by`` with the quantiles of ``column`` as columns, e.g. ``_percentiles(f, "section", "duration", p95_ms=0.95)``."""
    if frame.empty:
        return pd.DataFrame(columns=list(named), index=pd.Index([], name=by), dtype="float64")
    table = frame.groupby(by)[column].quantile(list(named.values())).unstack()
    return table.rename(columns={q: name for name, q in named.items()}).round(4)  # 4 decimals: a CLS of 0.003 must not become 0.0


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    """The frame as a list of JSON-ready dicts: ``.reset_index().to_dict(orient="records")`` with NaN as ``None`` (``NaN`` is not JSON).
    The index (the grouping dimension) becomes the first column(s); an anonymous default index is dropped."""
    frame = frame.reset_index(drop=isinstance(frame.index, pd.RangeIndex) and frame.index.name is None)
    return frame.astype(object).where(frame.notna(), None).to_dict(orient="records")


def _days(frame: pd.DataFrame) -> pd.Index:
    """Every UTC day from the first to the last event, with no gaps: a day without events is a 0 on the chart, not a missing point."""
    if frame.empty:
        return pd.Index([], dtype=object)
    return pd.date_range(frame["timestamp"].min().floor("D"), frame["timestamp"].max().floor("D"), freq="D").strftime("%Y-%m-%d")


def _is_error(events: pd.DataFrame) -> pd.Series:
    """The derived ``is_error`` flag of technical events: an unhandled application error, a section load that ended in error, a login that
    failed with ``internal_error`` (the server failing, not a wrong password) or an API response with status >= 500. Domain refusals
    (400 for insufficient stock, ``invalid_credentials``) are not technical errors."""
    kind = events["event_type"]
    return (
        (kind == "application_error_occurred")
        | ((kind == "section_load_completed") & (_dimension(events, "outcome") == "error"))
        | ((kind == "login_failed") & (_dimension(events, "reason") == "internal_error"))
        | ((kind == "http_request_completed") & (_number(events, "status_code") >= 500))
    )


def _finding(severity: str, code: str, message: str, **evidence: Any) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "evidence": evidence}


# --- volume: how much telemetry there is and what dominates it --------------------------------------


def analyze_events_per_day(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Events per UTC day, oldest first, with a 0 for a day without events: ``[{"day": "2026-10-27", "events": 12}, ...]``."""
    events = load_events(session, None, start_date, end_date, environment, with_tags=False)  # counting needs no tags
    per_day = events.groupby("day").size().reindex(_days(events), fill_value=0)
    return _records(per_day.rename("events").rename_axis("day").to_frame())


def analyze_events_by_type(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Which event types dominate: events and share of the period's total per ``event_type``, most frequent first."""
    events = load_events(session, None, start_date, end_date, environment, with_tags=False)
    by_type = _count_series(events["event_type"]).rename("events").rename_axis("event_type").to_frame()
    by_type["share"] = _ratio(by_type["events"], pd.Series(len(events), index=by_type.index))
    return _records(by_type)


def analyze_events_by_source(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Events per emitting ``service`` (backoffice, api, website...) and ``environment``, most frequent first."""
    events = load_events(session, None, start_date, end_date, environment, with_tags=False)
    by_source = events.groupby(["service", "environment"]).size().rename("events").to_frame()
    return _records(by_source.sort_index().sort_values("events", ascending=False, kind="stable"))


def analyze_technical_coverage(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Events per technical event type of the catalogue, with a 0 and ``observed: false`` for the ones that never arrived: a type with 0
    rows is an instrumentation gap, not a healthy system (the report cannot say an API route is fast if ``http_request_completed`` is
    never emitted)."""
    events = load_events(session, TECHNICAL_EVENT_TYPES, start_date, end_date, environment, with_tags=False)
    coverage = events.groupby("event_type").size().reindex(list(TECHNICAL_EVENT_TYPES), fill_value=0).rename("events").rename_axis("event_type").to_frame()
    coverage["observed"] = coverage["events"] > 0
    return _records(coverage)


# --- errors -----------------------------------------------------------------------------------------


def analyze_error_rate_by_type(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """For each technical event type that occurred: how many events there were, how many were errors (see ``_is_error``) and the share.
    Worst rate first. An ``application_error_occurred`` is an error by definition (rate 1.0): the rate is informative for the types that
    can succeed or fail (``section_load_completed``, ``http_request_completed``, ``login_failed``)."""
    events = load_events(session, TECHNICAL_EVENT_TYPES, start_date, end_date, environment)
    events["is_error"] = _is_error(events)
    table = events.groupby("event_type").agg(events=("event_type", "size"), errors=("is_error", "sum"))
    table["error_rate"] = _ratio(table["errors"], table["events"])
    return _records(table.sort_index().sort_values("error_rate", ascending=False, kind="stable", na_position="last"))


def analyze_errors_per_day(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Technical failures per day and their rate over the technical events of that day (only those are loaded; the rate says "how many of
    the events that can fail did fail", so a burst of page views does not hide it). ``is_error`` is derived by ``_is_error``."""
    events = load_events(session, TECHNICAL_EVENT_TYPES, start_date, end_date, environment)
    events["is_error"] = _is_error(events)
    daily = events.groupby("day").agg(technical_events=("event_type", "size"), errors=("is_error", "sum")).reindex(_days(events), fill_value=0)
    daily["error_rate"] = _ratio(daily["errors"], daily["technical_events"])
    return _records(daily.rename_axis("day"))


def analyze_application_errors(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Unhandled application errors (``application_error_occurred``) per ``component`` and ``error_code``, most frequent first."""
    errors = load_events(session, ("application_error_occurred",), start_date, end_date, environment)
    errors = errors.assign(component=_dimension(errors, "component"), error_code=_dimension(errors, "error_code")).dropna(subset=["component", "error_code"])
    return _records(errors.groupby(["component", "error_code"]).size().rename("errors").to_frame().sort_index().sort_values("errors", ascending=False, kind="stable"))


# --- access and security ----------------------------------------------------------------------------


def analyze_auth_failure_rate(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Daily login failure rate: ``login_failed / (login_failed + login_succeeded)`` per UTC day, oldest first.

    Both event types are loaded together in ONE query (``event_type IN (...)``): a rate needs numerator and denominator from the same
    rows, and the ratio is computed in Pandas. A day without logins is listed with 0 attempts and a ``None`` rate (not 0 %: with no
    attempt there is nothing to fail). ``login_attempted`` is not in the denominator: it can still be in flight, an outcome cannot.
    """
    logins = load_events(session, ("login_failed", "login_succeeded"), start_date, end_date, environment, with_tags=False)
    counts = logins.groupby(["day", "event_type"]).size().unstack(fill_value=0).reindex(columns=["login_succeeded", "login_failed"], fill_value=0)
    counts = counts.reindex(_days(logins), fill_value=0).rename(columns={"login_succeeded": "succeeded", "login_failed": "failed"})
    counts["attempts"] = counts["succeeded"] + counts["failed"]
    counts["failure_rate"] = _ratio(counts["failed"], counts["attempts"])
    return _records(counts.rename_axis("day").rename_axis(columns=None))


def analyze_login_failures_by_reason(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Failed logins per ``reason`` (``invalid_credentials``, ``rate_limited``, ``internal_error``...), most frequent first."""
    failed = load_events(session, ("login_failed",), start_date, end_date, environment)
    return _records(_count_series(_dimension(failed, "reason")).rename("failures").rename_axis("reason").to_frame())


def analyze_login_latency(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """How long a login takes (``duration_ms``): count, p50 and p95 per ``outcome`` (``succeeded`` / ``failed``)."""
    logins = load_events(session, ("login_succeeded", "login_failed"), start_date, end_date, environment)
    logins["duration"] = _number(logins, "duration_ms")
    table = logins.groupby("event_type").agg(logins=("duration", "size")).join(_percentiles(logins, "event_type", "duration", p50_ms=0.5, p95_ms=0.95))
    return _records(table.rename(index={"login_succeeded": "succeeded", "login_failed": "failed"}).rename_axis("outcome"))


def analyze_access_denied(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """401/403 decided by the API (``authorization_denied``) per ``route_id`` and ``status_code``, most frequent first."""
    denied = load_events(session, ("authorization_denied",), start_date, end_date, environment)
    denied = denied.assign(route_id=_dimension(denied, "route_id"), status_code=_number(denied, "status_code")).dropna(subset=["route_id", "status_code"])
    denied = denied.assign(status_code=denied["status_code"].astype("int64"))
    return _records(denied.groupby(["route_id", "status_code"]).size().rename("denied").to_frame().sort_index().sort_values("denied", ascending=False, kind="stable"))


def analyze_access_denied_per_day(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """401/403 decisions per UTC day, with a 0 for the days without any."""
    denied = load_events(session, ("authorization_denied",), start_date, end_date, environment, with_tags=False)
    per_day = denied.groupby("day").size().reindex(_days(denied), fill_value=0)
    return _records(per_day.rename("denied").rename_axis("day").to_frame())


def analyze_sessions_expired(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Sessions the browser had to discard (``session_expired``) per ``reason`` (``token_expired`` / ``unauthorized_response``)."""
    expired = load_events(session, ("session_expired",), start_date, end_date, environment)
    return _records(_count_series(_dimension(expired, "reason")).rename("sessions").rename_axis("reason").to_frame())


# --- latency ----------------------------------------------------------------------------------------


def analyze_section_load_latency(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Time until a backoffice/website section is usable (``section_load_completed``), per ``section``: loads, errors, error rate, p50, p95
    and max, slowest p95 first. It is client-side availability, not the API's response time (plan, section 10)."""
    loads = load_events(session, ("section_load_completed",), start_date, end_date, environment)
    loads = loads.assign(section=_dimension(loads, "section"), duration=_number(loads, "duration_ms"), is_error=_dimension(loads, "outcome") == "error")
    loads = loads.dropna(subset=["section"])
    sections = loads.groupby("section").agg(loads=("duration", "size"), errors=("is_error", "sum"), max_ms=("duration", "max"))
    sections = sections.join(_percentiles(loads, "section", "duration", p50_ms=0.5, p95_ms=0.95))
    sections["error_rate"] = _ratio(sections["errors"], sections["loads"])
    sections["over_target"] = sections["p95_ms"] > SECTION_LOAD_P95_TARGET_MS  # NaN (no durations) compares False
    return _records(sections.sort_index().sort_values("p95_ms", ascending=False, kind="stable", na_position="last"))


def analyze_section_load_latency_per_day(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Section load times per UTC day: loads, p50 and p95 (the trend of ``analyze_section_load_latency``)."""
    loads = load_events(session, ("section_load_completed",), start_date, end_date, environment)
    loads["duration"] = _number(loads, "duration_ms")
    daily = loads.groupby("day").agg(loads=("duration", "size")).join(_percentiles(loads, "day", "duration", p50_ms=0.5, p95_ms=0.95))
    return _records(daily.rename_axis("day"))


def analyze_web_vitals(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """Core Web Vitals reported by the browser, per ``metric``: readings, p75 (the percentile Google assesses them at) and how many were
    rated good / needs-improvement / poor by the browser itself. CLS is unitless; the others are milliseconds."""
    vitals = load_events(session, ("web_vital_reported",), start_date, end_date, environment)
    rating = _dimension(vitals, "rating")
    vitals = vitals.assign(
        metric=_dimension(vitals, "metric"), reading=_number(vitals, "value"), is_good=rating == "good", is_needs_improvement=rating == "needs-improvement", is_poor=rating == "poor"
    ).dropna(subset=["metric"])
    metrics = vitals.groupby("metric").agg(
        readings=("reading", "size"), good=("is_good", "sum"), needs_improvement=("is_needs_improvement", "sum"), poor=("is_poor", "sum")
    )
    metrics = metrics.join(_percentiles(vitals, "metric", "reading", p75=0.75))
    metrics["poor_rate"] = _ratio(metrics["poor"], metrics["readings"])
    return _records(metrics)


def analyze_http_by_route(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """API requests (``http_request_completed``) per ``route``: requests, 5xx count and rate, p50 and p95 latency, busiest first. Domain
    statuses (400, 404...) are not technical failures (plan, section 10); only 5xx counts. Empty while the API does not emit the event
    (``analyze_technical_coverage`` says so)."""
    requests = load_events(session, ("http_request_completed",), start_date, end_date, environment)
    requests = requests.assign(route=_dimension(requests, "route_id"), duration=_number(requests, "duration_ms"), is_error=_number(requests, "status_code") >= 500)
    requests = requests.dropna(subset=["route"])
    routes = requests.groupby("route").agg(requests=("duration", "size"), server_errors=("is_error", "sum"))
    routes = routes.join(_percentiles(requests, "route", "duration", p50_ms=0.5, p95_ms=0.95))
    routes["error_rate"] = _ratio(routes["server_errors"], routes["requests"])
    return _records(routes.sort_index().sort_values("requests", ascending=False, kind="stable"))


def analyze_http_per_day(session: Session, start_date=None, end_date=None, environment=None) -> list[dict[str, Any]]:
    """API requests per UTC day: requests, 5xx count and p95 latency (the trend of ``analyze_http_by_route``)."""
    requests = load_events(session, ("http_request_completed",), start_date, end_date, environment)
    requests = requests.assign(duration=_number(requests, "duration_ms"), is_error=_number(requests, "status_code") >= 500)
    daily = requests.groupby("day").agg(requests=("duration", "size"), server_errors=("is_error", "sum"))
    return _records(daily.join(_percentiles(requests, "day", "duration", p95_ms=0.95)).rename_axis("day"))


# --- findings ---------------------------------------------------------------------------------------


def derive_findings(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """What a person should look at first, from the computed metrics. Each finding names its evidence; severities are ``critical``
    (something is failing), ``warning`` (over a proposed threshold) and ``info`` (the report itself is blind). It only compares the
    metrics with the thresholds: it is not one of the metric functions."""
    findings: list[dict[str, Any]] = []

    application = metrics["application_errors"]
    if application:
        total = sum(row["errors"] for row in application)
        findings.append(_finding("critical", "application_errors", f"{total} unhandled application error(s); most frequent: {application[0]['component']}/{application[0]['error_code']} ({application[0]['errors']}).", total=total, by_component_and_code=application))

    auth = metrics["auth_failure_rate"]
    failed, completed = sum(row["failed"] for row in auth), sum(row["attempts"] for row in auth)
    if completed >= MIN_SAMPLE_FOR_RATE_ALERT and failed / completed > LOGIN_FAILURE_RATE_ALERT:
        findings.append(_finding("warning", "login_failure_rate", f"{failed / completed:.0%} of {completed} completed logins failed (proposed alert: >{LOGIN_FAILURE_RATE_ALERT:.0%}).", failed=failed, completed=completed, by_reason=metrics["login_failures_by_reason"]))
    internal = next((row for row in metrics["login_failures_by_reason"] if row["reason"] == "internal_error"), None)
    if internal:
        findings.append(_finding("critical", "login_internal_error", "Logins failed with internal_error: that is the server failing, not wrong credentials.", count=internal["failures"]))

    for row in metrics["section_load_latency"]:
        if row["over_target"]:
            findings.append(_finding("warning", "slow_section", f"Section '{row['section']}' p95 load is {row['p95_ms']:.0f} ms (target <{SECTION_LOAD_P95_TARGET_MS} ms).", **row))
        if row["errors"]:
            findings.append(_finding("critical", "section_load_errors", f"Section '{row['section']}' ended in error in {row['errors']} of {row['loads']} load(s).", **row))

    for row in metrics["web_vitals"]:
        if row["poor"]:
            findings.append(_finding("warning", "poor_web_vital", f"{row['metric']} rated poor in {row['poor']} of {row['readings']} reading(s); p75 = {row['p75']}.", **row))

    for row in metrics["http_by_route"]:
        if row["error_rate"] and row["error_rate"] > API_ERROR_RATE_ALERT:
            findings.append(_finding("critical", "api_5xx_rate", f"Route '{row['route']}' returned 5xx in {row['error_rate']:.1%} of {row['requests']} request(s).", **row))
        if row["p95_ms"] is not None and row["p95_ms"] > API_P95_ALERT_MS:
            findings.append(_finding("warning", "api_slow_route", f"Route '{row['route']}' p95 latency is {row['p95_ms']:.0f} ms (proposed alert: >{API_P95_ALERT_MS} ms).", **row))

    denied = metrics["access_denied"]
    if denied:
        findings.append(_finding("warning", "authorization_denied", f"{sum(row['denied'] for row in denied)} request(s) denied (401/403); most affected route: {denied[0]['route_id']}.", by_route=denied))

    missing = [row["event_type"] for row in metrics["technical_coverage"] if not row["observed"]]
    if missing:
        findings.append(_finding("info", "instrumentation_gap", f"No events of {len(missing)} technical type(s): the report cannot say anything about them.", not_observed=missing))

    order = {"critical": 0, "warning": 1, "info": 2}
    return sorted(findings, key=lambda finding: order[finding["severity"]])


# --- the pipeline -----------------------------------------------------------------------------------


def build_report(session: Session, start_date: datetime | None = None, end_date: datetime | None = None, environment: str | None = None) -> dict[str, Any]:
    """Every metric of the period, the findings derived from them and whether the period was too big to read whole:
    ``{"metrics": {name: [rows]}, "findings": [...], "truncated": bool}``. Expensive (one query per metric): callers go through
    ``report.get_report``, which caches it. The period is already resolved: it is only passed on."""
    period = (session, start_date, end_date, environment)
    metrics: dict[str, Any] = {
        "events_per_day": analyze_events_per_day(*period),
        "events_by_type": analyze_events_by_type(*period),
        "events_by_source": analyze_events_by_source(*period),
        "technical_coverage": analyze_technical_coverage(*period),
        "error_rate_by_type": analyze_error_rate_by_type(*period),
        "errors_per_day": analyze_errors_per_day(*period),
        "application_errors": analyze_application_errors(*period),
        "auth_failure_rate": analyze_auth_failure_rate(*period),
        "login_failures_by_reason": analyze_login_failures_by_reason(*period),
        "login_latency": analyze_login_latency(*period),
        "access_denied": analyze_access_denied(*period),
        "access_denied_per_day": analyze_access_denied_per_day(*period),
        "sessions_expired": analyze_sessions_expired(*period),
        "section_load_latency": analyze_section_load_latency(*period),
        "section_load_latency_per_day": analyze_section_load_latency_per_day(*period),
        "web_vitals": analyze_web_vitals(*period),
        "http_by_route": analyze_http_by_route(*period),
        "http_per_day": analyze_http_per_day(*period),
    }
    return {"metrics": metrics, "findings": derive_findings(metrics), "truncated": window_is_truncated(*period)}
