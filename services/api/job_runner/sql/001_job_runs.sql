-- Reference DDL for PostgreSQL / Supabase. Idempotent. (The job creates the table by itself if it is missing: see database.ensure_table.)
-- The control log of the background jobs: one row per EXECUTION of a job (today `nightly_export`).
-- It is the orchestration layer's log; it is NOT `reporting.pipeline_runs` (the ETL's own log of its phases).
--
-- status: pending -> processing -> completed | failed
--   pending    the row exists, the work has not started
--   processing set at the start of the work; THIS STATE IS THE LOCK
--   completed  everything went well
--   failed     an error; error_message says which

create table if not exists job_runs (
  id uuid primary key default gen_random_uuid(),
  job_name text not null,                          -- which job: 'nightly_export'
  target_date date not null,                       -- the day the run is about (UTC): what makes the job idempotent per day
  status varchar(16) not null default 'pending'
    constraint ck_job_runs_status check (status in ('pending', 'processing', 'completed', 'failed')),
  started_at timestamptz,                          -- when it became 'processing'
  finished_at timestamptz,                         -- when it became 'completed' or 'failed'
  error_message text,                              -- the exception's message, with no credential in it
  created_at timestamptz not null default now()
);

-- "Is that day already done?": quick. Not unique: every execution is recorded, so a day that failed can be tried again.
create index if not exists ix_job_runs_job_name_target_date on job_runs (job_name, target_date);

-- THE LOCK, enforced by the database: at most one row in 'processing' per job, even if two processes start at the same instant.
-- It is a constraint on the status column itself, not a second locking mechanism: there is no lock table, column or file.
create unique index if not exists uq_job_runs_one_processing_per_job on job_runs (job_name) where status = 'processing';
