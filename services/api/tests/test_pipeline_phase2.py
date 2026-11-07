"""Phase 2 of the ticket, written in the code and not only configured: explicit retries with their justification,
explicit handling of a failure with ``return_state=True``, and a cache with its own ``cache_key_fn`` and ``cache_expiration``."""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace
import textwrap
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine

from data.pipelines import pipeline
from data.process import weekly_performance as wp

DATABASE_TASKS = ["start_pipeline_run", "finish_pipeline_run", "extract_kpi_events", "count_window_events", "load_weekly_performance"]
SOURCE = inspect.getsource(pipeline)


def _decorator_keywords(task_name: str) -> dict[str, ast.expr]:
    tree = ast.parse(SOURCE)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == task_name)
    call = next(d for d in function.decorator_list if isinstance(d, ast.Call))
    return {k.arg: k.value for k in call.keywords if k.arg}


# ---------------------------------------------------------------- 1. retries, explicit and justified


@pytest.mark.parametrize("name", DATABASE_TASKS)
def test_every_task_that_touches_the_database_spells_out_retries_and_retry_delay_seconds(name):
    keywords = _decorator_keywords(name)
    assert "retries" in keywords and "retry_delay_seconds" in keywords


@pytest.mark.parametrize("name", ["resolve_week_window", "validate_kpi_events", "check_currency_consistency", "deduplicate_events",
                                  "calculate_total_material_cost", "count_kits_delivered", "count_shortage_events", "count_cost_variance_events", "build_weekly_kpi_rows",
                                  "reconcile_weekly_kpis", "save_raw_snapshot", "save_eval_report"])
def test_the_tasks_that_do_not_touch_an_external_service_have_no_retries(name):
    assert "retries" not in _decorator_keywords(name)


def test_the_number_of_retries_is_justified_in_a_comment_next_to_where_it_is_set():
    lines = SOURCE.splitlines()
    at = next(i for i, line in enumerate(lines) if line.startswith("_DELAYS = _retry_delays()"))
    comment = []
    for line in reversed(lines[:at]):
        if not line.startswith("#"):
            break
        comment.append(line)
    text = " ".join(reversed(comment))
    assert "WHY 3 RETRIES" in text and "5 s" in text and "30 s" in text and "2 min" in text
    assert "Why not more" in text  # it explains the upper limit too, not only the number


def test_the_default_values_are_three_retries_waiting_5_30_and_120_seconds(monkeypatch):
    monkeypatch.delenv("PIPELINE_RETRIES", raising=False)
    monkeypatch.delenv("PIPELINE_RETRY_DELAYS", raising=False)
    delays = pipeline._retry_delays()
    assert delays == [5, 30, 120] and len(delays) == 3
    assert sum(delays) < pipeline.repository.STALE_AFTER.total_seconds()  # the whole back-off fits far inside the dead-run limit


# ---------------------------------------------------------------- 2. a failure handled explicitly with return_state=True


def test_the_flow_handles_a_failed_optional_task_itself_instead_of_letting_it_propagate():
    flow = ast.parse(textwrap.dedent(inspect.getsource(pipeline.weekly_office_performance_flow.fn))).body[0]
    states = [n for n in ast.walk(flow) if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
              and any(k.arg == "return_state" for k in n.value.keywords)]
    assert len(states) >= 1
    # and the flow itself asks the state whether it completed, and reads the error when it did not
    source = inspect.getsource(pipeline.weekly_office_performance_flow.fn)
    assert "count_state.is_completed()" in source and "raise_on_failure=False" in source


# ---------------------------------------------------------------- 3. the cache of the transformation


def clean(order_id="o-1", cost="10.00", programme="ventas-b2b"):
    return wp.CleanEvent(wp.INBOUND, "valencia", programme, "EUR", order_id, Decimal(cost))


WEEK = date(2026, 10, 26)


def key(events, task="calculate_total_material_cost", **extra):
    context = SimpleNamespace(task=SimpleNamespace(name=task))
    return pipeline._kpi_cache_key(context, {"events": events, **extra})


def test_the_costly_transformation_has_its_own_cache_key_and_expiration():
    for name in ("calculate_total_material_cost", "count_kits_delivered", "count_shortage_events", "count_cost_variance_events"):
        task = getattr(pipeline, name)
        assert task.cache_key_fn is pipeline._kpi_cache_key
        assert task.cache_expiration == timedelta(hours=1)


def test_the_cache_key_is_the_kpi_plus_the_content_of_the_events():
    events = [clean("o-1"), clean("o-2", "5.00")]
    assert key(events) == key(list(events))  # same events, same KPI: same key
    assert key(events) == key(list(reversed(events)))  # the order the database returned them in does not matter
    assert key(events) != key(events[:1])  # an event less
    assert key(events) != key([clean("o-1"), clean("o-2", "5.01")])  # one amount changed
    assert key(events) != key(events, task="count_kits_delivered")  # another KPI never reuses this KPI's result
    assert key(events).startswith("kpi|calculate_total_material_cost|")


def test_a_refresh_has_no_cache_key_so_that_call_computes_again():
    assert key([clean("o-1")], refresh=True) is None
    assert key([clean("o-1")], refresh=False) is not None


def test_the_cache_key_of_the_extraction_is_the_database_the_environment_and_the_window(tmp_path):
    one = create_engine(f"sqlite:///{tmp_path / 'a.sqlite'}")
    two = create_engine(f"sqlite:///{tmp_path / 'b.sqlite'}")
    start = datetime(2026, 10, 26, tzinfo=timezone.utc)

    def extraction_key(source, environment="production", start=start):
        return pipeline._extract_cache_key(None, {"source": source, "start": start, "end": start + timedelta(days=7), "environment": environment})

    assert extraction_key(one) == extraction_key(one)
    assert extraction_key(one) != extraction_key(two)  # another database
    assert extraction_key(one) != extraction_key(one, environment="staging")  # another environment
    assert extraction_key(one) != extraction_key(one, start=start + timedelta(days=7))  # another week


def test_the_key_comments_say_what_defines_the_key_and_how_long_it_is_valid():
    key_doc = inspect.getdoc(pipeline._kpi_cache_key) or ""
    assert "CACHE KEY OF THE KPI TASKS" in key_doc and "fingerprint" in key_doc
    assert "CACHE KEY OF THE EXTRACTION" in (inspect.getdoc(pipeline._extract_cache_key) or "")
    assert "CACHE_TTL = 1 hour" in SOURCE  # the validity is stated where the task is declared
