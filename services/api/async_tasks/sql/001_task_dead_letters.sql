-- The dead-letter queue of the asynchronous tasks (ticket DEV-55): one row per task that failed for good.
-- The worker creates this table by itself the first time it needs it (async_tasks/dlq.py: ensure_table); this file is the reference, and what to run
-- by hand if the database role of the worker cannot create tables. PostgreSQL (Supabase) and SQLite understand it as it is.

CREATE TABLE IF NOT EXISTS task_dead_letters (
    id          SERIAL PRIMARY KEY,            -- SQLite: INTEGER PRIMARY KEY AUTOINCREMENT
    task_id     VARCHAR(64)  NOT NULL,         -- the id POST /reporting/pipeline-runs/async returned
    task_name   VARCHAR(128) NOT NULL,
    attempt     INTEGER      NOT NULL,         -- the attempt that failed last (1 = the first execution)
    error       TEXT         NOT NULL,         -- the error message, without credentials
    arguments   VARCHAR(1000),                 -- the light arguments of the task, as JSON text
    failed_at   TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_task_dead_letters_task_id ON task_dead_letters (task_id);
