// Shapes of the /reporting API (services/api/reporting/schemas.py): the weekly KPIs per office and programme, and the status of the pipeline run
// that computed them. The names are the ones of the briefing's destination table (weekly_office_program_performance).

export type Office = "valencia" | "miami";
export type Currency = "EUR" | "USD";

/** One office and programme of one week, with the four KPIs. `total_material_cost` is in `currency` (valencia is EUR, miami is USD). */
export interface WeeklyEntry {
  office: Office;
  programme_id: string;
  total_material_cost: number;
  kits_delivered_count: number;
  shortage_events_count: number;
  cost_variance_events_count: number;
  currency: Currency;
}

/** `GET /reporting/weekly-office-program-performance`: `week_start` is the Monday (UTC) of the week the entries cover. */
export interface WeeklyReport {
  week_start: string;
  entries: WeeklyEntry[];
}

export type RunState = "Running" | "Completed" | "Failed" | "Crashed" | "Skipped";

/** `GET /reporting/pipeline-runs/latest`: only what the dashboard needs to say how fresh the numbers are. */
export interface PipelineRun {
  state: RunState;
  week_start: string;
  started_at: string;
  finished_at: string | null;
  error: string | null;
}
