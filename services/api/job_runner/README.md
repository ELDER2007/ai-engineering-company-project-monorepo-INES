# `job_runner` — control of the background jobs

The `job_runs` table and the state machine that moves it. Today it controls one job: `nightly_export` ([`scripts/nightly_export.py`](../../../scripts/nightly_export.py), ticket DEV-53).
Nothing here imports FastAPI: a background job is a process of its own, and the API never starts it.

| File | What it is |
| --- | --- |
| `models.py` | the `job_runs` table (SQLModel) and the four states |
| `service.py` | the ONLY place that knows how a row changes state: `create_job_run`, `start_processing`, `complete`, `fail`, `discard_pending`, `mark_stale_as_failed`, `has_processing_lock`, `has_completed_for_date`, `latest`, `list_runs` |
| `database.py` | the connection (the API's `DATABASE_URL`), opened by the job's own process |
| `sql/001_job_runs.sql` | reference DDL for PostgreSQL / Supabase (the job also creates the table by itself if it is missing) |

## The table

| Column | Meaning |
| --- | --- |
| `id` | uuid of the execution |
| `job_name` | which job (`nightly_export`) |
| `target_date` | the UTC day the run is about. **Mandatory: it is what makes the job idempotent per day** |
| `status` | `pending`, `processing`, `completed` or `failed` (a `CHECK` allows nothing else) |
| `started_at`, `finished_at` | when it became `processing`, and when it ended |
| `error_message` | the exception's message when it failed, with no credential in it |
| `created_at` | when the row was created |

Indexes: `(job_name, target_date)` — plain, **not unique**, because every execution is recorded and a day that failed can be tried again — and the lock (below).

## The state machine

```
pending ──▶ processing ──▶ completed
                      └──▶ failed
```

* **pending**: the row exists before any work is done.
* **processing**: set at the start, before any work. **This state is the lock.**
* **completed / failed**: the end. Both release the lock. `failed` keeps the error.

## The lock is the state itself

There is no lock table, lock column or lock file. If a row of `nightly_export` is `processing`, the next run gives up silently. What makes that true when
two processes start at the same instant (both look, both see nobody) is a constraint **on the same `status` column**: a partial unique index,

```sql
create unique index uq_job_runs_one_processing_per_job on job_runs (job_name) where status = 'processing';
```

A second row that tries to become `processing` is refused by the database (`JobAlreadyRunning`), not by a check the application did a moment before.
`has_processing_lock` is only a quick way to give up early; `start_processing` is what the database enforces. An instance that loses removes its own
`pending` row (`discard_pending`): it leaves no trace, so it cannot become a zombie.

## No record is left in `processing`

* **Inside the process**: a `try/except/finally` marks the row `failed` with the error message on *any* exception, Ctrl-C and SIGTERM included; the error is
  logged and propagated, not swallowed. If writing the `failed` fails, it is tried again; and a last `finally` closes the row if it somehow ended without a final state.
* **A process that is killed** (`kill -9`, a power cut) cannot write anything. Its row would stay `processing` and block every night for ever, so the next run
  starts with `mark_stale_as_failed`: a row `processing` for longer than `NIGHTLY_STALE_AFTER_MINUTES` (default 120, and always longer than the pipeline's timeout)
  is closed as `failed`.

## Not `pipeline_runs`

`job_runs` is the orchestration layer: *what the night did* (export the CSV, launch the pipeline, lock, idempotency). `reporting.pipeline_runs` is the ETL's own log
(its phases, its watermark, the rows it processed), written by the pipeline's process while it runs. The job writes the first and never reads or writes the second;
neither is the lock of the other.

## Tests

```bash
python -m pytest tests/background_processes          # SQLite; a real PostgreSQL if NIGHTLY_TEST_ADMIN_URL is set
```
