// Mirrors GET /telemetry/report (services/api/telemetry/router.py, ReportResponse; the metrics come from
// services/api/telemetry/analysis.py) — keep in sync manually. Only the metrics the dashboard draws are typed; the
// endpoint returns more. A rate is null when its denominator is 0 ("no data" is not "0 %").

export interface DayEvents {
  day: string; // "YYYY-MM-DD", UTC
  events: number;
}

export interface TypeShare {
  event_type: string;
  events: number;
  share: number | null;
}

export interface ErrorDay {
  day: string;
  technical_events: number;
  errors: number;
  error_rate: number | null;
}

export interface AuthFailureDay {
  day: string;
  succeeded: number;
  failed: number;
  attempts: number;
  failure_rate: number | null;
}

export interface SectionLatency {
  section: string;
  loads: number;
  errors: number;
  error_rate: number | null;
  p50_ms: number | null;
  p95_ms: number | null;
  max_ms: number | null;
  over_target: boolean;
}

export type FindingSeverity = "critical" | "warning" | "info";

export interface Finding {
  severity: FindingSeverity;
  code: string; // what the dashboard translates by
  message: string; // the API's own text, in English: the fallback for a code the dashboard does not know
  evidence?: Record<string, unknown>; // the numbers behind the message
}

export interface TechnicalReport {
  period: { from: string; to: string };
  metrics: {
    events_per_day: DayEvents[];
    events_by_type: TypeShare[];
    errors_per_day: ErrorDay[];
    auth_failure_rate: AuthFailureDay[];
    section_load_latency: SectionLatency[];
  };
  findings: Finding[];
  generated_at: string;
  truncated: boolean; // the period had more events than the report reads
  cached: boolean;
  cache_age_seconds: number;
}
