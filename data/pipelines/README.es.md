# Carpeta `data/pipelines`

Esta carpeta agrupa **todos los pipelines de datos del monorepo** relacionados con la compañía: procesos de ingesta, ETL/ELT, limpieza, transformación y carga hacia sistemas analíticos o de producción.

Cada subcarpeta o archivo dentro de `data/pipelines/` debe representar **un pipeline o conjunto de jobs** (por ejemplo `sales-etl`, `telemetry-stream`, `customer-segmentation`) e incluir la configuración necesaria (scripts, orquestación, conectores, esquemas, etc.).

- **Propósito principal**: unificar en un único lugar la lógica de movimiento y transformación de datos que soporta las aplicaciones y analíticas de la compañía.
- **Recomendación**: documenta aquí los pipelines que vayas añadiendo, describiendo su objetivo, orígenes/destinos de datos, dependencias y cómo ejecutarlos en desarrollo, pruebas y producción.

## `weekly_office_performance` (pipeline de desempeño de negocio)

El reporte semanal por oficina y programa para Laura (CEO) y Elena (L&D). Flow de Prefect 3, punto de entrada [`pipeline.py`](./pipeline.py), especificación [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md), detalles en [`weekly_office_performance/README.md`](./weekly_office_performance/README.md).

```bash
python data/pipelines/pipeline.py                      # última semana ISO completa (datos demo en un clon limpio)
python data/pipelines/pipeline.py --week-start 2026-10-26 --refresh
```

Lee `telemetry_events` (solo lectura) y escribe `reporting.weekly_office_program_performance`; los archivos intermedios van a `data/raw/` y el informe de validación de cada corrida a `data/eval/`.
