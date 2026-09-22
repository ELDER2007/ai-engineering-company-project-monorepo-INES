# Nexova API (`services/api`)

Centralized FastAPI backend for Nexova, per [docs/ARCHITECTURE_PROPOSAL.md](../../docs/ARCHITECTURE_PROPOSAL.md): one app, one router per domain.

## Domains implemented

- **`incidents/`** — Support ticket CSV analysis ("Analizador de Incidencias"). Validates and computes metrics on Nexova support-incident exports, per the rules in [incidents-analysis/CONTEXT-nexova.md](../../incidents-analysis/CONTEXT-nexova.md). Reuses the same [`incidents_analyzer`](../../packages/incidents_analyzer) package as the CLI script in `incidents-analysis/analyze.py`, so both run identical validation/metrics logic.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/incidents/analyze` | Upload a CSV (`multipart/form-data`, field name `file`), get back the analysis as JSON. `400` if the file isn't `.csv`, `422` if required columns are missing or the file has no data rows. |
| `GET` | `/api/incidents/results/export` | Download the most recent analysis as `results.csv` (one metric per row). `404` if no analysis has run yet in this process. |
| `GET` | `/health` | Liveness check. |

Interactive docs (Swagger UI) are available at `/docs` when the server is running.

## Running locally

```bash
cd services/api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

`ALLOWED_ORIGINS` (comma-separated) controls CORS; defaults to the local Vite dev ports (`5173`, `5174`) used by `uis/website` and `uis/backoffice` when unset. Set it explicitly in production — see `docs/ARCHITECTURE_PROPOSAL.md` section 4.4.

## Known limitation

The "last analysis" used by the export endpoint is kept in an in-memory, module-level variable — it is lost on restart and is not shared across multiple worker processes. Acceptable for this feature's current scope; documented rather than hidden.
