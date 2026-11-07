-- Two database roles for the weekly pipeline (design, section 4.5): least privilege.
--
--   pipeline_reader : can ONLY read `telemetry_events`. It cannot write anywhere, so the pipeline cannot change telemetry
--                     even by mistake.
--   pipeline_writer : can ONLY read and write the two tables of the `reporting` schema. It cannot read telemetry.
--
-- Run it ONCE, as an administrator (in Supabase: SQL editor), AFTER 001_reporting_schema.sql has created the `reporting`
-- schema and its tables. Replace BOTH passwords before running; never commit the real ones. It is idempotent apart from
-- `create role`: run the two `create role` lines only the first time.

create role pipeline_reader login password 'CHANGE-ME-reader-password';
create role pipeline_writer login password 'CHANGE-ME-writer-password';

-- Neither role is allowed to create anything in the database or in `public`.
revoke create on schema public from pipeline_reader, pipeline_writer;

-- The reader: one table, read only.
grant usage on schema public to pipeline_reader;
grant select on public.telemetry_events to pipeline_reader;

-- The writer: the two tables of the reporting schema, and nothing else.
grant usage on schema reporting to pipeline_writer;
grant select, insert, update, delete on reporting.weekly_office_program_performance to pipeline_writer;
grant select, insert, update, delete on reporting.pipeline_runs to pipeline_writer;

-- Check (run as the administrator): each role must have exactly the privileges above.
--   select grantee, table_schema, table_name, string_agg(privilege_type, ', ' order by privilege_type)
--   from information_schema.role_table_grants
--   where grantee in ('pipeline_reader', 'pipeline_writer')
--   group by 1, 2, 3 order by 1, 2, 3;
