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

## Probarlo (desde la raíz del repo)

```bash
cd services/api && uv sync && cd ../..
services/api/.venv/bin/python -m data.pipelines.pipeline --demo --week-start 2026-10-26
```

`--demo` usa una base de datos desechable (`data/.local/demo.sqlite`) con eventos de ejemplo, nunca la de la aplicación.
Sin `--demo` lee `telemetry_events` de la base de la API (`DATABASE_URL`, o su SQLite local) en modo solo lectura, y por defecto solo del entorno `production`
(`--environment` o `PIPELINE_ENVIRONMENT` para cambiarlo).

Cada corrida deja: una fila en `reporting.pipeline_runs`, la copia de los eventos leídos en `data/raw/` y un informe en `data/eval/`.

Sin servidor Prefect, Prefect levanta uno temporal (unos segundos) en cada corrida.

## Tests

```bash
cd services/api && uv run pytest tests/test_weekly_performance.py tests/test_reporting.py tests/test_pipeline_resilience.py
```
