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
| Reintentos en servicios externos | `extract_kpi_events`, `load_weekly_performance` y el log reintentan 3 veces (5 s, 30 s, 2 min) |
| Corre como script | `python data/pipelines/pipeline.py ...` (código de salida 0 / 1) |
| No repite lo que corrió hace menos de 1 h | Caché de 1 h en `extract_kpi_events` y en las 4 tasks de KPI (`calculate_total_material_cost`, `count_kits_delivered`, `count_shortage_events`, `count_cost_variance_events`); `--refresh` la salta. La carga nunca se cachea |

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

## Con tu base real: ¿por qué sale vacío?

El comando sin argumentos lee solo eventos del entorno `production`, porque un reporte que lee el liderazgo no debe mezclar pruebas. Si en tu base los eventos son de otro entorno (lo normal mientras desarrollas es `development`), el reporte sale con **0 filas** y la corrida termina bien: no es un error, es el filtro funcionando.

Para ver tus datos de prueba, di el entorno **y la semana** de tus eventos:

```bash
python data/pipelines/pipeline.py --environment development --week-start 2026-10-26
```

**Cuidado con una cosa:** la tabla de destino no lleva el entorno en su clave (así lo fija el briefing) y cada corrida reemplaza la semana completa. Por eso una corrida de `production` sobre una semana en la que antes corriste `development` **retira** esas filas (y al revés). No es un fallo: es la regla de reemplazo. Si quieres conservar las filas de prueba, no ejecutes `production` sobre esa misma semana.

## En producción: programarlo, guardar las credenciales y recibir avisos

Todo esto es **opcional**: sin nada de esto, el comando de arriba funciona igual que siempre.

| Qué | Cómo | Dónde está |
| --- | --- | --- |
| Que corra solo (lunes 05:00 UTC y corrección el jueves 05:00 UTC) | `python data/pipelines/deploy.py --work-pool nexova-reporting` y un worker: `prefect worker start --pool nexova-reporting`. `--dry-run` muestra el plan sin servidor | `../deploy.py` |
| Credenciales en `Secret` blocks en lugar de variables de entorno | `python -m data.pipelines.weekly_office_performance.blocks` los crea (imprime solo los nombres) y `PIPELINE_SECRET_BLOCKS=1` los activa | `blocks.py` |
| Aviso cuando falla, se cae o los datos pueden estar mal | `PIPELINE_ALERT_WEBHOOK_URL` (o el block `pipeline-alert-webhook`): un *webhook* compatible con Slack. Sin él no hace nada | `alerts.py` |

Qué está comprobado y qué no, en `../PIPELINE_DESIGN.md` (secciones 4.5, 4.6 y 8b): los tests usan un servidor de Prefect temporal y un *webhook* local; no se ha registrado en un servidor real ni se ha enviado un aviso a un Slack real.

## Tests

Tests del pipeline (en la raíz del proyecto, no necesitan la API):

```bash
python -m pytest tests/pipelines                       # todos
python -m pytest tests/pipelines/test_pipeline.py      # unitarios de las tasks de transformación (sin base de datos, 1-2 s)
python -m pytest tests/pipelines/test_subflows.py      # cada subflow por separado
python -m pytest tests/pipelines/test_cli.py           # la línea de comandos del pipeline y su documentación
```

Tests de comportamiento del pipeline y de sus endpoints (necesitan la API):

```bash
cd services/api && uv run pytest tests/test_pipeline_*.py tests/test_reporting*.py tests/test_weekly_performance.py
```
