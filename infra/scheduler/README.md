# `infra/scheduler` — the trigger of the nightly job (ticket DEV-53)

A container of its own that runs [`scripts/nightly_export.py`](../../scripts/nightly_export.py) every night at **02:00 UTC**.

```bash
docker compose --profile scheduler up -d scheduler     # start it
docker compose logs -f scheduler                        # what it does, one line per event
docker compose --profile scheduler stop scheduler       # stop it
```

It is **off by default**: a plain `docker compose up` starts `api` and `uis` exactly as before. It needs `DATABASE_URL` in the `.env` of the
repo root (in production, the one that lives on the VPS), the same database as the API. Without it the container refuses to start the job
(`NIGHTLY_REQUIRE_DATABASE_URL=1`) instead of "working" against a throw-away file inside itself.

## The cron expression

```
0 2 * * *        every day at 02:00 UTC        (infra/scheduler/crontab)
```

| Field | Value | Meaning |
| --- | --- | --- |
| minute | `0` | on the hour |
| hour | `2` | 02:00 |
| day of month, month, day of week | `* * *` | every day |

**Why 02:00 UTC.** The UTC day being exported ended two hours before (clients that were offline send their events late), it is a time with
little traffic, and it does not coincide with the pipeline's own schedule (Monday and Thursday at 05:00 UTC). The container runs with
`TZ=UTC`, so the hour does not depend on the time zone of the server.

## The decision: a dedicated scheduler container

The ticket leaves the trigger open: the `crontab` of the operating system, a scheduler of the framework, or a dedicated container. What was chosen,
and why:

| Option | Verdict |
| --- | --- |
| **Dedicated scheduler container** | **Chosen.** It is what the ticket recommends for production. |
| `crontab` of the VPS | Valid, and the line is below. It needs Python and every dependency installed on the server, and its hour is the server's. |
| A scheduler inside FastAPI (`APScheduler`, `@repeat_every`, a `lifespan` hook) | **Ruled out.** It would run in the API's own process: the first acceptance criterion forbids it. |

Why the container:

* **Independent of the API, completely.** It is another container: it does not share the process, the thread, the image or the lifecycle of the
  API (`depends_on` is not used). Restarting or crashing one never touches the other.
* **Reproducible.** Python, the dependencies and the pipeline's code travel in the image. Nothing has to be installed on the server.
* **One time zone, known.** UTC, always.
* **It can be tried here.** It was built and run with Docker with a schedule of one minute to check that it fires (see *How it was checked*).
* **It respects the other projects.** Only new files (`infra/scheduler/`) and one more service in `docker-compose.yml`, under a Compose *profile*:
  `api`, `uis` and their images are not touched.

The alternative, if the container is not wanted, is one line in the `crontab` of the server (with `CRON_TZ=UTC` if its cron supports it, or
the hour converted):

```
0 2 * * *  cd /path/to/repo && /path/to/python scripts/nightly_export.py >> /var/log/nightly_export.log 2>&1
```

## What is in the image

Only what the job needs: the API's `core` (the database URL), the `job_runner`, the `data/pipelines` and `data/process` the job launches, the script
and the schedule. **Not** `services/api/.env` (never in an image) and **not** the API's routers or application. The dependencies are the ones of
`services/api/requirements.txt`. `supercronic` is downloaded at a pinned version and checked against the sha256 that its release publishes.

## Running it by hand, and for another day

```bash
docker compose --profile scheduler run --rm scheduler python scripts/nightly_export.py                       # yesterday, now
docker compose --profile scheduler run --rm -e TARGET_DATE=2026-10-30 scheduler python scripts/nightly_export.py   # a given past day
```

A night that was skipped (the container was stopped, the server was off) is not caught up by itself: the next night does only its own
yesterday. Run the missing day by hand with `TARGET_DATE`. Running a day twice is safe: a day already `completed` is skipped.

## How it was checked

Not only with unit tests: the image was built and run with Docker against a throw-away PostgreSQL 16, with the same command as the real crontab but a
schedule of one minute (a test crontab mounted over the real one), and the real pipeline:

* `supercronic -test` accepts `infra/scheduler/crontab`.
* The container fired by itself at the start of the minute, exported the 5 events of the day to the CSV, launched the real pipeline (40 s) and ended `completed`.
* The next minute it fired again and logged `status=skipped ... already completed`: no second CSV, no second pipeline, no second row.
* `job_runs` held one `completed` row; `reporting.pipeline_runs` held the pipeline's own row (`scheduled`, `Completed`, 17 events read, 5 rows written).
* The image holds no `.env` file, no router and no application of the API.

That run also found a real problem that no unit test could: the dependency resolver of `uv` picked FastAPI 0.162 with Prefect 3.8.8, which do not work together
(`TypeError: Body() got an unexpected keyword argument 'min_items'`), so the pipeline died inside the container. [`constraints.txt`](./constraints.txt) fixes the
versions for this image only.

