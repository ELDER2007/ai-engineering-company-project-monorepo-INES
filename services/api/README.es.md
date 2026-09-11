# `api` — Backend centralizado de Nexova (FastAPI)

El único servicio backend de Nexova, según la convención propia del
monorepo (ver [`AGENTS.md`](../../AGENTS.md) § `services/` y
[`services/README.md`](../README.md)): una sola app FastAPI con un módulo
de router por dominio, no un conjunto de microservicios.

Todavía nadie lo llama — el sitio público del Hito 1 simula el envío del
formulario del lado del cliente (ver
[`uis/website/README.es.md`](../../uis/website/README.es.md)). Esto es solo
el esqueleto para que el trabajo de backend futuro (envíos del formulario de
talento, CRUD de candidatos/vacantes, tickets, …) tenga dónde caer según la
convención del repo, en vez de quedar disperso en otro lugar.

## Estructura

```
api/
├── requirements.txt
├── .env.example
└── app/
    ├── main.py           # app FastAPI(), incluye los routers
    └── routers/
        └── health.py     # GET /health — el único endpoint real por ahora
```

Para añadir un router de dominio nuevo: `app/routers/<dominio>.py` y
`include_router` en `app/main.py` — por ejemplo `app/routers/candidates.py`,
`app/routers/vacancies.py`, `app/routers/talent.py`.

## Cómo ejecutarlo

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

- `GET /` → `{"service": "nexova-api", "status": "ok"}`
- `GET /health` → `{"status": "ok"}`
- `GET /docs` → Swagger UI interactivo (viene gratis con FastAPI)

Autocontenido como las apps de `uis/`: su propio `requirements.txt`, sin
tooling de Python compartido en la raíz todavía (ver los huecos de tooling
en `memory-bank/techContext.md`).

> _These instructions are also available in [English](./README.md)._
