# weekly_office_performance

Pipeline Prefect del "Reporte Semanal de Desempeño por Oficina y Programa". Diseño: [`../PIPELINE_DESIGN.md`](../PIPELINE_DESIGN.md).

| Pieza | Archivo |
| --- | --- |
| Flow + tasks (orquestación) | `flow.py` |
| Lógica pura (agregación, validación) | `data/process/weekly_performance.py` |
| Tablas / conexiones (`reporting`) | `storage.py`, `sql/001_reporting_schema.sql` |
| Datos demo de telemetría (solo dev local) | `seed_telemetry.py` |

## Ejecutar (desde la raíz del repo)

```bash
cd services/api && uv sync && cd ../..
services/api/.venv/bin/python -m data.pipelines.weekly_office_performance --seed --week-start 2026-10-26
```

Sin `DATABASE_URL` usa un SQLite local en `data/.local/` (gitignored). Con `DATABASE_URL`
(o `REPORTING_DATABASE_URL` / `TELEMETRY_DATABASE_URL` por separado) usa PostgreSQL/Supabase;
ahí aplica antes `sql/001_reporting_schema.sql` (o deja que la API cree el esquema al arrancar).

Sin servidor Prefect, Prefect levanta uno temporal (unos segundos) en cada corrida. Para
programarlo cada lunes 05:00 UTC hace falta un servidor/worker y un deployment (pendiente).

## API

`GET /reporting/weekly-office-program-performance`, `GET /reporting/pipeline-runs/latest`,
`POST /reporting/pipeline-runs` (módulo `services/api/reporting/`). Tests: `services/api/tests/test_reporting.py`
y `test_weekly_performance.py`.
