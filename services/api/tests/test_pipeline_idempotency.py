"""Phase 3 of the ticket: the load is idempotent (anchored on the briefing's unique constraint) and every run leaves
its minimum execution metadata (start, end, records processed, final state, error)."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from data.pipelines.weekly_office_performance import repository, storage
from test_reporting import PERF, WEEK, add_event, data_dir, engines, rows, run  # noqa: F401  (fixtures and helpers)

REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module", autouse=True)
def prefect_harness():
    with prefect_test_harness():
        yield


def table(target):
    """The whole destination table, every column, in a stable order."""
    with target.connect() as connection:
        return [dict(r) for r in connection.execute(select(PERF).order_by(PERF.c.office, PERF.c.programme_id, PERF.c.week_start)).mappings()]


# ---------------------------------------------------------------- the briefing is the source of truth


def briefing_table() -> str:
    path = next(REPO.glob("pipeline*BRIEFING*.md"), None)
    if path is None:
        pytest.skip("the pipeline briefing is not in the repository")
    match = re.search(r"create table reporting\.weekly_office_program_performance \((.*?)\n\);", path.read_text(encoding="utf-8"), re.S)
    assert match, "the briefing has no destination table"
    return match.group(1)


def test_the_destination_table_has_exactly_the_columns_of_the_briefing():
    wanted = [line.split()[0] for line in briefing_table().splitlines() if line.strip() and not line.strip().startswith("unique")]
    assert [c.name for c in PERF.columns] == wanted


def test_the_unique_constraint_of_the_briefing_is_the_one_the_upsert_relies_on(engines):
    briefing = re.search(r"unique \((.*?)\)", briefing_table()).group(1).replace(" ", "").split(",")
    assert briefing == ["office", "programme_id", "week_start"]
    assert list(storage.UPSERT_CONFLICT_COLUMNS) == briefing  # the ON CONFLICT target
    uniques = sa_inspect(engines[1]).get_unique_constraints("weekly_office_program_performance", schema="reporting")
    assert [u["column_names"] for u in uniques] == [briefing]  # and the database really has it


def test_the_database_refuses_a_duplicate_of_the_key_so_the_constraint_is_what_protects_the_table(engines):
    run(engines)
    first = table(engines[1])[0]
    duplicate = {**first, "id": __import__("uuid").uuid4()}
    with pytest.raises(IntegrityError):
        with engines[1].begin() as connection:
            connection.execute(insert(PERF).values(**duplicate))


# ---------------------------------------------------------------- 3.1 the load is idempotent


def test_two_runs_over_the_same_range_leave_the_destination_table_identical(engines):
    run(engines)
    after_one = table(engines[1])
    run(engines)
    assert table(engines[1]) == after_one  # every column, id and computed_at included


def test_many_runs_still_leave_it_identical(engines):
    run(engines)
    after_one = table(engines[1])
    for _ in range(3):
        run(engines)
    assert table(engines[1]) == after_one and len(after_one) == 5


def test_a_repeated_run_reports_that_it_changed_nothing(engines):
    run(engines)
    again = run(engines)
    log = repository.get_run(engines[1], again.run_id)
    assert (log.rows_written, log.rows_changed, log.rows_deleted) == (5, 0, 0)


def test_a_changed_source_replaces_the_values_it_never_adds_to_them(engines):
    source, target = engines
    run(engines)
    before = {(r["office"], r["programme_id"]): r for r in table(target)}
    add_event(source, "outbound_order_created", {"office": "valencia", "programme_id": "ventas-b2b", "currency": "EUR", "order_id": "extra-1"})
    run(engines)
    run(engines)  # and again: the new value must not be added a second time
    after = {(r["office"], r["programme_id"]): r for r in table(target)}
    key = ("valencia", "ventas-b2b")
    assert after[key]["kits_delivered_count"] == before[key]["kits_delivered_count"] + 1  # +1, not +2
    assert after[key]["id"] == before[key]["id"]  # the same row, updated in place
    untouched = [k for k in before if k != key]
    assert all(after[k] == before[k] for k in untouched)  # the other rows were not touched at all


def test_runs_over_other_weeks_do_not_disturb_the_week(engines):
    run(engines)
    after_one = [r for r in table(engines[1]) if r["week_start"] == WEEK]
    run(engines, week=date(2026, 10, 19))
    assert [r for r in table(engines[1]) if r["week_start"] == WEEK] == after_one
    assert {r["week_start"] for r in table(engines[1])} == {WEEK, date(2026, 10, 19)}


def test_the_same_week_asked_through_any_of_its_days_is_the_same_range(engines):
    run(engines, week=date(2026, 10, 26))  # Monday
    after_one = table(engines[1])
    run(engines, week=date(2026, 11, 1))  # the Sunday of the same ISO week
    assert table(engines[1]) == after_one


def test_a_failed_attempt_between_two_good_runs_does_not_change_the_result(engines, monkeypatch):
    run(engines)
    good = table(engines[1])
    monkeypatch.setattr(repository, "_verify_load", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("died mid-load")))
    with pytest.raises(RuntimeError):
        run(engines)
    monkeypatch.undo()
    run(engines)
    assert table(engines[1]) == good


# ---------------------------------------------------------------- 3.2 the minimum execution metadata of every run


def test_a_completed_run_records_start_end_records_processed_state_and_no_error(engines):
    before = datetime.now(timezone.utc)
    log = repository.get_run(engines[1], run(engines).run_id)
    assert before.replace(microsecond=0) <= log.started_at.replace(tzinfo=timezone.utc) <= log.finished_at.replace(tzinfo=timezone.utc)  # start, then end
    assert (log.events_read, log.rows_written) == (17, 5)  # records processed: in and out
    assert log.state == "Completed" and log.error is None


def test_a_failed_run_records_the_error_it_caught_and_still_closes_its_log(engines):
    add_event(engines[0], "outbound_order_created", {"office": "miami", "programme_id": "x", "currency": "EUR", "order_id": "bad-1"})
    with pytest.raises(Exception, match="miami/EUR"):
        run(engines)
    log = repository.get_latest_run(engines[1])
    assert log.state == "Failed" and "CurrencyMismatchError" in log.error and "miami/EUR" in log.error
    assert log.started_at is not None and log.finished_at is not None  # never left open
    assert log.events_read == 18  # how far it got: the records it did process before failing


def test_every_run_gets_its_own_row_and_the_history_is_kept(engines):
    ids = {run(engines).run_id for _ in range(3)}
    with engines[1].connect() as connection:
        stored = connection.execute(text("select count(*) from reporting.pipeline_runs")).scalar()
    assert len(ids) == 3 and stored == 3


def test_the_log_lives_in_the_database_next_to_the_results_in_the_reporting_schema(engines):
    run(engines)
    assert "pipeline_runs" in sa_inspect(engines[1]).get_table_names(schema="reporting")
    columns = {c["name"] for c in sa_inspect(engines[1]).get_columns("pipeline_runs", schema="reporting")}
    assert {"started_at", "finished_at", "events_read", "rows_written", "state", "error"} <= columns
