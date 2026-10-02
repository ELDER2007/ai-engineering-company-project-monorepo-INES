from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from incidents_analyzer import analyze, format_report, read_rows, to_export_rows


VALID_ROW = {
    "ticket_id": "NXV-000001",
    "date": "2025-01-31",
    "client_company": "Example Ltd",
    "category": "TECHNICAL",
    "description": "Cannot access account",
    "agent_id": "AGT-07",
    "status": "OPEN",
    "customer_email": "person@example.test",
    "satisfaction_score": "",
}


@pytest.mark.parametrize(
    ("field", "value", "rule"),
    [
        ("ticket_id", "invalid", "invalid_or_missing_ticket_id"),
        ("date", "2025-02-30", "invalid_or_missing_date"),
        ("status", "UNKNOWN", "invalid_or_missing_status"),
    ],
)
def test_invalid_required_fields_are_counted(field: str, value: str, rule: str) -> None:
    row = {**VALID_ROW, field: value}

    result = analyze([row], "probe.csv")

    assert result.invalid_records == 1
    assert getattr(result.invalid_breakdown, rule) == 1


def test_duplicate_ticket_ids_invalidate_each_duplicate() -> None:
    rows = [VALID_ROW.copy(), {**VALID_ROW, "status": "CLOSED", "satisfaction_score": "5"}]

    result = analyze(rows, "probe.csv")

    assert result.invalid_records == 2
    assert result.invalid_breakdown.duplicate_ticket_id == 2


def test_reader_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="Missing required columns"):
        read_rows(StringIO("ticket_id\nNXV-000001\n"))


def test_sample_csv_matches_documented_metrics() -> None:
    project_root = Path(__file__).resolve().parents[3]
    rows = read_rows(str(project_root / "data/raw/incidents-nexova.csv"))

    result = analyze(rows, "incidents-nexova.csv")

    assert (result.total_records, result.valid_records, result.invalid_records) == (100, 96, 4)
    assert result.category_counts == {
        "TECHNICAL": 28,
        "BILLING": 18,
        "ACCESS": 21,
        "HR_QUERY": 17,
        "COMPLAINT": 12,
    }
    assert result.status_counts == {"OPEN": 27, "CLOSED": 56, "DISCARDED": 13}
    assert result.satisfaction.counts == {1: 2, 2: 5, 3: 10, 4: 22, 5: 17}
    assert result.satisfaction.average == 3.84


def test_customer_emails_never_appear_in_report_or_export() -> None:
    private_email = "unique-private@example.test"
    row = {**VALID_ROW, "customer_email": private_email}

    result = analyze([row], "probe.csv")
    output = format_report(result) + repr(to_export_rows(result))

    assert private_email not in output
