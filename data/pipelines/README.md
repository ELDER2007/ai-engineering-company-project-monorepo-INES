# `data/pipelines` folder

This folder groups **all data pipelines in the monorepo** related to the company: ingestion, ETL/ELT, cleaning, transformation, and loading into analytical or production systems.

Each subfolder or file under `data/pipelines/` should represent **one pipeline or job set** (for example `sales-etl`, `telemetry-stream`, `customer-segmentation`) and include the required configuration (scripts, orchestration, connectors, schemas, etc.).

- **Main purpose**: consolidate in one place the data movement and transformation logic that powers the company’s applications and analytics.
- **Recommendation**: document pipelines as you add them—their goal, data sources and sinks, dependencies, and how to run them in development, testing, and production.

> _Spanish version: [README.es.md](./README.es.md)._

## `weekly_office_performance` (business performance pipeline)

The weekly report per office and programme for Laura (CEO) and Elena (L&D). Prefect 3 flow, entry point [`pipeline.py`](./pipeline.py), specification [`PIPELINE_DESIGN.md`](./PIPELINE_DESIGN.md), details in [`weekly_office_performance/README.md`](./weekly_office_performance/README.md).

```bash
python data/pipelines/pipeline.py                      # last complete ISO week (demo data on a fresh checkout)
python data/pipelines/pipeline.py --week-start 2026-10-26 --refresh
```

It reads `telemetry_events` (read-only) and writes `reporting.weekly_office_program_performance`; intermediate files go to `data/raw/` and the validation report of each run to `data/eval/`.
