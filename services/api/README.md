# `api` — Nexova centralized backend (FastAPI)

The one backend service for Nexova, per the monorepo's own convention (see
[`AGENTS.md`](../../AGENTS.md) § `services/` and
[`services/README.md`](../README.md)): a single FastAPI app with one router
module per domain, not a set of microservices.

Nothing calls this yet — the Hito 1 public site simulates its form
submission client-side (see
[`uis/website/README.md`](../../uis/website/README.md)). This is just the
skeleton so future backend work (talent-form submissions, candidate/vacancy
CRUD, tickets, …) has a place to land per the repo's convention instead of
getting scattered elsewhere.

## Structure

```
api/
├── requirements.txt
├── .env.example
└── app/
    ├── main.py           # FastAPI() app, includes routers
    └── routers/
        └── health.py     # GET /health — the only real endpoint so far
```

Add a new domain router as `app/routers/<domain>.py` and `include_router`
it in `app/main.py` — e.g. `app/routers/candidates.py`,
`app/routers/vacancies.py`, `app/routers/talent.py`.

## Running it

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- `GET /` → `{"service": "nexova-api", "status": "ok"}`
- `GET /health` → `{"status": "ok"}`
- `GET /docs` → interactive Swagger UI (from FastAPI, no extra setup)

Self-contained like the `uis/` apps: its own `requirements.txt`, no shared
root-level Python tooling yet (see the tooling gaps in
`memory-bank/techContext.md`).

> _Estas instrucciones también están disponibles en [español](./README.es.md)._
