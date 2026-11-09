# weekly_office_performance

Pipeline Prefect del "Reporte Semanal de Desempeño por Oficina y Programa". Especificación: [`../PIPELINE_DESIGN.md`](../PIPELINE_DESIGN.md). Punto de entrada: [`../pipeline.py`](../pipeline.py).

| Pieza | Archivo |
| --- | --- |
| Flow + tasks (orquestación) | `data/pipelines/pipeline.py` |
| Cálculos puros (validar, deduplicar, agregar, conciliar) | `data/process/weekly_performance.py` |
| Todo el SQL | `repository.py` |
| Tablas del esquema `reporting`, conexiones | `storage.py`, `sql/001_reporting_schema.sql` |
| Lo único que `services/` puede importar | `interface.py` |
| Datos demo (solo local y tests) | `seed_telemetry.py` |

## Resiliencia (lo que exige el ticket)

| Requisito | Cómo se cumple |
| --- | --- |
| Tolera fallos parciales | Tasks **opcionales** (`count_window_events`, `save_raw_snapshot`, `save_eval_report`): si fallan se anota en `warnings` y la corrida sigue. Las críticas la detienen |
| Reintentos en servicios externos | `extract_events`, `load_weekly_performance` y el log reintentan 3 veces (5 s, 30 s, 2 min) |
| Corre como script | `python data/pipelines/pipeline.py ...` (código de salida 0 / 1) |
| No repite lo que corrió hace menos de 1 h | Caché de 1 h en `extract_events` y `aggregate_by_office_programme`; `--refresh` la salta. La carga nunca se cachea |

## Probarlo (desde la raíz del repo)

```bash
cd services/api && uv sync && cd ../..
services/api/.venv/bin/python data/pipelines/pipeline.py
```

Sin argumentos lee la última semana completa. En un clon limpio (sin `DATABASE_URL` y sin telemetría local) lo avisa y usa datos de demostración, para que el comando funcione siempre.

`--demo` fuerza una base de datos desechable (`data/.local/demo.sqlite`) con eventos de ejemplo, nunca la de la aplicación.
Sin `--demo` lee `telemetry_events` de la base de la API (`DATABASE_URL`, o su SQLite local) en modo solo lectura, y por defecto solo del entorno `production`
(`--environment` o `PIPELINE_ENVIRONMENT` para cambiarlo).

Cada corrida deja: una fila en `reporting.pipeline_runs`, la copia de los eventos leídos en `data/raw/` y un informe en `data/eval/`.

Sin servidor Prefect, Prefect levanta uno temporal (unos segundos) en cada corrida.

## Verlo por la API, con cifras (datos de demostración)

En un clon limpio la API arranca, pero `GET /reporting/weekly-office-program-performance` responde `404 No week has been computed yet`: su base de datos no tiene
eventos de telemetría y el pipeline no tiene nada que calcular. Para ver cifras **sin tocar la base de la propia API**, la API puede leer la base de
demostración desechable del pipeline. Dos comandos, desde la raíz del repo:

```bash
# 1) El pipeline en modo demostración: crea data/.local/demo.sqlite con eventos de ejemplo y calcula la semana 2026-10-26.
python data/pipelines/pipeline.py --demo

# 2) La API, leyendo los datos de reporting de ese archivo (el resto de la API sigue con su base de siempre).
DEMO="$(pwd)/data/.local/demo.sqlite"
cd services/api
REPORTING_DATABASE_URL="sqlite:///$DEMO" TELEMETRY_DATABASE_URL="sqlite:///$DEMO" \
AUTH_INITIAL_EMAIL=tu@correo.com AUTH_INITIAL_PASSWORD=elige-una-contraseña \
uvicorn main:app --port 8000
```

`AUTH_INITIAL_EMAIL` / `AUTH_INITIAL_PASSWORD` solo crean el primer usuario cuando **todavía no hay ninguno**; si la API ya tiene cuentas, usa una de ellas.

Después, en `http://localhost:8000/docs`, *Authorize* con ese correo y contraseña y `GET /reporting/weekly-office-program-performance`: cinco filas (dos oficinas, tres
programas) de la semana 2026-10-26. `GET /reporting/pipeline-runs/latest` muestra la corrida y `POST /reporting/pipeline-runs` (admin) la repite.

> **No** ejecutes `seed_telemetry.py` contra la base de la propia API: **borra todas las filas de `telemetry_events`** antes de cargar los eventos de demostración.
> Es solo para archivos desechables, que es lo que usa `--demo`.

## Tests

```bash
cd services/api && uv run pytest tests/test_weekly_performance.py tests/test_reporting.py tests/test_pipeline_resilience.py tests/test_pipeline_ticket.py
```
