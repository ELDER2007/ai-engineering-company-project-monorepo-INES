"""Request/response shapes of the reporting API."""

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
    id: str
    flow_name: str
    trigger: str
    state: str
    week_start: date | None
    events_read: int
    rejected_count: int
    rows_written: int
    error: str | None
    started_at: datetime
    finished_at: datetime


class PipelineRunCreate(BaseModel):
    """Body of ``POST /reporting/pipeline-runs``. Optional: omit to run the last complete week."""

    week_start: date | None = None
