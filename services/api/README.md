# Nexova API (`services/api`)

Centralized FastAPI backend for Nexova, per [docs/ARCHITECTURE_PROPOSAL.md](../../docs/ARCHITECTURE_PROPOSAL.md): one app, one router per domain.

## Domains implemented

- **`incidents/`** — Support ticket CSV analysis ("Analizador de Incidencias"). Validates and computes metrics on Nexova support-incident exports, per the rules in [scripts/CONTEXT-nexova.md](../../scripts/CONTEXT-nexova.md). Reuses the same [`incidents_analyzer`](../../packages/incidents_analyzer) package as the CLI script in `scripts/analyze.py`, so both run identical validation/metrics logic.
- **`suppliers/`** — Supplier directory ("Directorio de Proveedores", Patricia Solís / Nexova). Replaces the HR spreadsheet with a [TinyDB](https://tinydb.readthedocs.io/)-backed store, seeded on startup with the 15 suppliers from [`suppliers/seed_data.py`](./suppliers/seed_data.py) (spec: [CONTEXT-suppliers.md](./suppliers/CONTEXT-suppliers.md)). Pydantic (`suppliers/schemas.py`) rejects with `422` any missing `country`, a `status` outside `active`/`suspended`, empty `categories`, or a `currency` that doesn't match the country (Spain→EUR, USA→USD). Suspending (not deleting) is the preferred way to retire a supplier.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/incidents/analyze` | Upload a CSV (`multipart/form-data`, field name `file`), get back the analysis as JSON. `400` if the file isn't `.csv`, `422` if required columns are missing or the file has no data rows. |
| `GET` | `/api/incidents/results/export` | Download the most recent analysis as `results.csv` (one metric per row). `404` if no analysis has run yet in this process. |
| `GET` | `/api/suppliers` | List all suppliers. |
| `GET` | `/api/suppliers/search/by-country?country=Spain\|USA` | Filter by country. |
| `GET` | `/api/suppliers/search/by-category?category=...` | Filter by category (one of `job_boards`, `ats_software`, `assessment_tools`, `training_platforms`, `payroll_and_hr_software`, `video_interview`, `background_check`, `office_and_facilities`, `it_and_software_licenses`). |
| `GET` | `/api/suppliers/{id}` | Get one supplier. `404` if missing. |
| `POST` | `/api/suppliers` | Create a supplier. `422` on invalid data. |
| `PATCH` | `/api/suppliers/{id}` | Partial update. Changing `monthly_rate` stamps `updated_at` (audit). The merged record is re-validated, so changing `country` alone (currency mismatch) is a `422`. |
| `PATCH` | `/api/suppliers/{id}/rate` | Update the monthly rate (`{"monthly_rate": 350}`). Always stamps `updated_at` with the time of the change. `422` if the rate is `<= 0`; `404` if the supplier doesn't exist. |
| `PATCH` | `/api/suppliers/{id}/status` | Activate/suspend (`{"status": "active" \| "suspended"}`). |
| `DELETE` | `/api/suppliers/{id}` | Remove a supplier (`204`). `404` if it doesn't exist. The CONTEXT prefers suspending to keep the relationship history; use this for entries made by mistake. |
| `GET` | `/health` | Liveness check. |

Interactive docs (Swagger UI) are available at `/docs` when the server is running.

## Running locally

```bash
cd services/api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

To (re)load the initial suppliers into TinyDB by hand (the API also seeds an empty database on startup):

```bash
uv run seed              # seed only if empty
uv run seed --reset      # wipe and reload the 15 initial suppliers
```

`uv run seed` uses the `seed` script declared in `pyproject.toml` (uv installs the dependencies on first run). Run it from `services/api`; from the repo root use `uv run --project services/api seed`, since the root has no Python project. `python seed.py` works too if the dependencies are already installed.

`ALLOWED_ORIGINS` (comma-separated) controls CORS; defaults to the local Vite dev ports (`5173`, `5174`) used by `uis/website` and `uis/backoffice` when unset. Set it explicitly in production — see `docs/ARCHITECTURE_PROPOSAL.md` section 4.4.

## Known limitations

- The "last analysis" used by the export endpoint is kept in an in-memory, module-level variable — it is lost on restart and is not shared across multiple worker processes. Acceptable for this feature's current scope; documented rather than hidden.
- The suppliers directory is stored at `suppliers/db.json`, a TinyDB flat file that's regenerated (and reseeded) whenever it's missing — it's gitignored, not source. A second worker process would not see writes made by another one; fine for the current single-process scope, and the reason the project brief already earmarks a move to Postgres once the ORM is ready.
