# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## Scripts

### `train_sales_forecast.py` — Nexova's sales forecast

Trains and evaluates the monthly revenue forecast of [`BRIEFING_NEXOVA_SALES.md`](../BRIEFING_NEXOVA_SALES.md).

- **What it does**: loads `data/raw/nexova_sales.csv` and checks its columns; treats empty values (never with later months); splits by time (8 years to train, the 2 most recent to test); builds causal features; trains a Random Forest whose settings are chosen by time validation inside the training years (why Random Forest: [`data/process/sales_model.py`](../data/process/sales_model.py)); evaluates MSE, PSI, Gini and K² Score on the test years; writes `metrics.json` and the picture of the forecast with its range to [`data/eval/sales_forecast/`](../data/eval/sales_forecast/README.md). The seed is fixed (42).
- **Requirements**: [`uv`](https://docs.astral.sh/uv/); the libraries are those of the root `pyproject.toml` / `uv.lock` (Python 3.12).
- **Usage**, from the root of the repository (about a minute):
  ```bash
  uv run python scripts/train_sales_forecast.py
  uv run python scripts/train_sales_forecast.py --compare          # also compares Random Forest with XGBoost (training years only)
  uv run python scripts/train_sales_forecast.py --data other.csv --output /tmp/results
  uv run pytest tests/pipelines                                    # its tests
  ```

### `analyze.py` — Nexova incident CSV analyzer

Validates and computes metrics on a Nexova support-incident CSV export, per the rules in [`CONTEXT-nexova.md`](./CONTEXT-nexova.md).

- **What it does**: loads the CSV, flags invalid records (missing/out-of-range fields, one rule type per issue), and prints totals, an invalid-records breakdown by rule, category/status distribution with percentages, and the average satisfaction score for closed tickets. Offers to export the results to `results.csv` (one metric per row).
- **Requirements**: Python 3.10+, no third-party packages — install the shared validation/metrics package in editable mode once: `pip install -e packages/shared/incidents_analyzer`.
- **Usage**:
  ```bash
  python scripts/analyze.py data/raw/incidents-nexova.csv
  ```
- **Same logic as the API**: the validation/metrics code lives in [`packages/shared/incidents_analyzer`](../packages/shared/incidents_analyzer) and is reused as-is by the `incidents` domain in [`services/api`](../services/api), so the script and the API can never drift apart.
- **Privacy**: never prints, logs, or exports individual `customer_email` values, per the stakeholder note in `CONTEXT-nexova.md`.

### `seed_incidents.py` — load the CSV history into the incident manager

Loads the historical helpdesk export into the incident manager's database (`services/api/incidents/db.json`).

- **What it does**: validates every row with the shared `incidents_analyzer` rules, transforms it (`description → title`, `date → created_at`, status and category maps, optional `location`/`ubicacion` column → `branch`, default `central`) and inserts it with `origin: "customer"`. Invalid rows are **not** inserted: they are listed with their line, id and broken rules (never the email). Idempotent: ids already stored are skipped, never overwritten. It ends by checking that `/api/incidents/summary` matches the metrics expected from the transformed CSV (exit code `1` if not).
- **Requirements**: the API's environment (pydantic, tinydb…): `cd services/api && python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- **Usage**:
  ```bash
  services/api/.venv/bin/python scripts/seed_incidents.py              # data/raw/incidents-nexova.csv
  services/api/.venv/bin/python scripts/seed_incidents.py --reset      # wipe the incidents first
  services/api/.venv/bin/python scripts/seed_incidents.py --csv other.csv --db /tmp/incidents.json
  ```
- **Details and mapping table**: [`services/api/README.md`](../services/api/README.md#incident-manager). The CONTEXT does not define the maps; they live in [`packages/shared/incidents/contract.json`](../packages/shared/incidents/contract.json).

### `nightly_export.py` — the nightly telemetry export (ticket DEV-53)

Every night: exports the telemetry of the previous UTC day to a CSV, launches the data pipeline, and records in the database what happened.

- **What it does**: writes `data/raw/telemetry_YYYY-MM-DD.csv` from `telemetry_events` (only if the file does not exist; a **backup** for audit and recovery, not an input of the pipeline), launches `data/pipelines/pipeline.py` as a subprocess, and keeps one row per execution in the table `job_runs` (`pending → processing → completed | failed`). Lock, idempotency and zombie handling: top of the script and [`services/api/job_runner/README.md`](../services/api/job_runner/README.md).
- **A process of its own**: it imports no FastAPI and never runs inside the API. It is started from outside, every night, by the scheduler container ([`infra/scheduler/`](../infra/scheduler/README.md), `0 2 * * *` UTC).
- **Requirements**: the API's environment (`services/api/requirements.txt`) and a database: `DATABASE_URL` (also read from `services/api/.env`).
- **Usage**:
  ```bash
  python scripts/nightly_export.py                            # yesterday, in UTC
  TARGET_DATE=2026-10-30 python scripts/nightly_export.py     # a given past day, with no change in the code
  ```
- **Exit code**: `0` done or skipped (already done / another run is going), `1` it failed, `2` bad usage, `130` interrupted.
- **Privacy**: the CSV is telemetry; `data/raw/telemetry_*.csv` is git-ignored. Credentials in an error never reach the table or the log.

## Exit codes

`0` = it worked. `1` = it failed (missing or unreadable input, damaged data); `2` = wrong command-line usage (`analyze.py`). The message goes to stderr. A script never ends with `0` after failing.
