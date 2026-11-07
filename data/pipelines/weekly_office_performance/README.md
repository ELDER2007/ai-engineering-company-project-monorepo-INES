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

## Tests

Tests del pipeline (en la raíz del proyecto, no necesitan la API):

```bash
python -m pytest tests/pipelines                       # todos
python -m pytest tests/pipelines/test_pipeline.py      # unitarios de las tasks de transformación (sin base de datos, 1-2 s)
python -m pytest tests/pipelines/test_subflows.py      # cada subflow por separado
python -m pytest tests/pipelines/test_cli.py           # el comando python data/pipelines/pipeline.py y su documentación
```

Tests de comportamiento del pipeline y de sus endpoints (necesitan la API):

```bash
cd services/api && uv run pytest tests/test_pipeline_*.py tests/test_reporting*.py tests/test_weekly_performance.py
```
