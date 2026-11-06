-- Reference DDL for PostgreSQL / Supabase. Idempotent.
-- Everything the weekly pipeline writes lives under the dedicated `reporting` schema.
-- The pipeline only reads `telemetry_events`; it never writes there.

create schema if not exists reporting;

create table if not exists reporting.weekly_office_program_performance (
  id uuid primary key default gen_random_uuid(),
  office text not null,
  programme_id text not null,
  week_start date not null,
  total_material_cost numeric not null default 0,
  kits_delivered_count integer not null default 0,
  shortage_events_count integer not null default 0,
  cost_variance_events_count integer not null default 0,
  currency text not null,
  computed_at timestamptz not null default now(),
  unique (office, programme_id, week_start)
);

-- The execution log: one row per run. Backs GET /reporting/pipeline-runs/latest.
create table if not exists reporting.pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  flow_name text not null,
  trigger text not null,                  -- scheduled | manual
  prefect_flow_run_id text,
  week_start date not null,
  environment text not null,              -- telemetry environment that was read
  state text not null,                    -- Running | Completed | Failed | Crashed | Skipped
  started_at timestamptz not null,
  finished_at timestamptz,
  events_read integer not null default 0,
  window_events_total integer not null default 0,
  rejected_count integer not null default 0,
  rows_written integer not null default 0,
  rows_changed integer not null default 0,
  rows_deleted integer not null default 0,
  error text
);

-- The lock against concurrent runs: at most one `Running` run per flow and week, enforced by the database.
create unique index if not exists uq_pipeline_runs_one_running_per_week
  on reporting.pipeline_runs (flow_name, week_start)
  where state = 'Running';
