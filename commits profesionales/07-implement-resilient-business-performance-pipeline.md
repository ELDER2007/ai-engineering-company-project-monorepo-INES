Implement resilient business performance pipeline

The part 1 design described a weekly pipeline for Laura (CEO) and Elena
(L&D) but nothing ran it. Build it on the real telemetry, so that a failure
in the middle of a run can neither corrupt nor duplicate what is already
loaded, and so that it can run unattended.

Pipeline (data/pipelines/pipeline.py, Prefect 3)
- One flow and twelve tasks, grouped as extract, transform and load, that
  read telemetry_events read-only and write
  reporting.weekly_office_program_performance
- Read the real columns of the table (timestamp, tags) and the cost as
  total_cost_minor, converted from cents. Count each (event_type, order_id)
  once and never mix euros and dollars
- Read only one telemetry environment, production by default: the contract
  marks events development, test, staging or production, and a leadership
  report must not count tests
- Keep the events a run read in data/raw and its validation report in
  data/eval

Resilience
- Tasks are critical or optional. The optional ones (a count of every event
  of the window, the raw snapshot and the report) are called with
  return_state=True: if one fails it is recorded in a warnings column and the
  run goes on. An unknown count is stored as null, never as zero
- The tasks that touch the database retry three times, waiting 5 s, 30 s and
  2 min, which covers a closed connection, a saturated pooler and a short
  failover; a longer wait would only hide a real outage. The reason is a
  comment next to the numbers
- Cache the extraction and the aggregation for one hour, with their own
  cache_key_fn; never cache the load, the run log or the checks, and never a
  failure. A refresh option, used by the manual trigger, bypasses it so a late
  event is not hidden

Idempotency and audit
- Load in one transaction: upsert on the briefing's unique constraint,
  replacing the values, only when one of them differs, so a repeated run
  leaves the table identical, id and computed_at included. Delete the rows of
  the week that no longer have events and verify the count before committing
- Log every run in reporting.pipeline_runs (17 fields). A partial unique
  index makes the database refuse a second Running run of the same week; a
  Running run older than one hour is marked Crashed, and an on_crashed hook
  does it at once when the process dies

Script and API
- Run it with python data/pipelines/pipeline.py, from any folder, exiting 0
  when it completes and 1 when it fails. On a fresh checkout, with no
  database configured, say so and use demo data; with a configured database
  never hide a failure behind the demo. Read the same .env as the API
- Add three routes under /reporting in services/api/reporting: status of the
  latest run, manual trigger (admins only) and the weekly KPIs, in the shape
  of the briefing. They need a session at router level, like the other
  domains, and only call the pipeline's interface module: no SQL, no ETL

Validation
- 168 tests of the pipeline and its routes, plus an end-to-end test that
  posts events to the real telemetry receiver and reads the report
- KPI values compared, cell by cell, with plain loops that follow the
  briefing's definitions, on the company's own telemetry fixture
- Run against SQLite, PostgreSQL 16 and the real Supabase

Not done
- Prefect Secret blocks, the deployment with the Monday and Thursday crons,
  alerts and subflows. Kits are counted per delivery order, as the briefing
  says, not per unit
