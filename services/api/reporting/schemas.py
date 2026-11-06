"""Request/response shapes of the reporting API (the vocabulary of the Nexova briefing)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class WeeklyEntry(BaseModel):
    office: Literal["valencia", "miami"]
    programme_id: str
    total_material_cost: float
    kits_delivered_count: int
    shortage_events_count: int
    cost_variance_events_count: int
    currency: Literal["EUR", "USD"]


class WeeklyReport(BaseModel):
    week_start: date
    entries: list[WeeklyEntry]


class PipelineRunOut(BaseModel):
    """One row of the execution log."""

    id: str
    flow_name: str
    trigger: Literal["scheduled", "manual"]
    prefect_flow_run_id: str | None
    week_start: date
    environment: str
    state: Literal["Running", "Completed", "Failed", "Crashed", "Skipped"]
    started_at: datetime
    finished_at: datetime | None
    events_read: int
    window_events_total: int | None  # null = unknown (never read it as zero)
    rejected_count: int
    rows_written: int
    rows_changed: int
    rows_deleted: int
    error: str | None
    warnings: str | None  # failures of optional tasks; the run still completed


class PipelineRunCreate(BaseModel):
    """Body of ``POST /reporting/pipeline-runs``. Optional: omit it to run the last complete week."""

    week_start: date | None = None
