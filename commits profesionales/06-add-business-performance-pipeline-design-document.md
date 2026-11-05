Add business performance pipeline design document

Laura (CEO) and Elena (L&D) have no weekly view of how Valencia and
Miami compare in training-material spend and delivery. The technical
telemetry report cannot give it: it groups by day, event type, source or
route, never by office and programme, it does not sum costs, it works on
a rolling 7-day window instead of closed ISO weeks, and its result is a
cached answer for engineers, not a table anyone can audit. Document the
design of a dedicated pipeline before writing any orchestration code.

Design (data/pipelines/PIPELINE_DESIGN.md)
- State the purpose in one sentence: the weekly consolidated report per
  office and programme, with the four KPIs of the briefing (material
  cost, kits delivered, shortage frequency, cost variance frequency),
  built on inbound_order_created, outbound_order_created,
  stock_threshold_triggered and kit_cost_variance_detected
- Describe the current state read from the real telemetry code, not from
  assumptions: the telemetry_events columns (timestamp, tags JSONB), the
  cost already travelling as total_cost_minor, and the eventId primary
  key that deduplicates at ingestion. No extra telemetry field is needed
- Specify the extraction (read-only SELECT of four event types in one ISO
  week, filtered by the indexed columns), the ETL flow as a Mermaid
  diagram, and the destination: reporting.weekly_office_program_performance
  with one row per office, programme and week, plus reporting.pipeline_runs
- Keep the three guarantees explicit. Idempotency: one transaction, a
  unique key and replace-not-add upserts, so a failed load rolls back and
  a rerun gives the same table. Observability: a 15-field run log, each
  field justified, with a control count to tell a real zero from a dead
  capture. Recoverability: no checkpoints, because recomputing a week is
  cheaper than trusting stale state, and a partial unique index so the
  cron and a manual run cannot load the same week at once
- Map it to Prefect: one flow, nine tasks grouped as extract, transform
  and load, the relevant states, and Secret blocks with a read-only role
  on telemetry_events and a write role limited to the reporting schema
- Design three endpoints under /reporting (status, manual trigger, KPI
  feed), each calling one function of data/pipelines through a single
  interface module, so services/ holds no SQL and no ETL logic. Use the
  company's own vocabulary: valencia/miami, ventas-b2b, EUR/USD
- Answer ten design questions (idempotency, observability,
  recoverability, concurrency) against the behaviour of this monorepo,
  and write down the limits: no arrival time column, no history of past
  values, and KPIs that can undercount because inventory events are
  emitted by the browser

Not touched
- services/api/telemetry/analysis.py, GET /telemetry/report and the
  telemetry_events table. The pipeline only reads from it
- No code: the prototype lives apart, in
  feature/weekly-performance-pipeline, and still uses old telemetry
  column names that part 2 must align
