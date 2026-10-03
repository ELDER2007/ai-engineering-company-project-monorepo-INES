#!/usr/bin/env python3
"""Nexova support-incident CSV analyzer (Phase 1 — CLI).

Usage:
    python analyze.py <path-to-csv>
    python scripts/analyze.py data/raw/incidents-nexova.csv

Validates every record against the rules in ``CONTEXT-nexova.md``, prints a
summary, and offers to export the results to ``results.csv`` (one metric per
row). Validation and metrics logic lives in the shared ``incidents_analyzer``
package (see ``packages/incidents_analyzer``) so the API in ``services/api``
runs the exact same code — see rule 4 of the project brief.

Never prints, logs, or exports individual customer_email addresses (see
CONTEXT-nexova.md, stakeholder note), even for invalid records.

Exit codes:
    0   the file was analysed (and exported, if asked)
    1   the file cannot be analysed: not found, unreadable, not UTF-8 text, not CSV, other
        columns than the required ones, or no data rows; or the results could not be saved
    2   wrong usage
    3   the file was analysed but not one record in it is valid
    130 interrupted with Ctrl+C
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from incidents_analyzer import analyze, format_report, missing_required_columns, to_export_rows


def _fail(message: str) -> int:
    print(f"Error: {message}", file=sys.stderr)
    return 1


def _read(csv_path: Path) -> list[dict[str, str]] | str:
    """The rows of the file, or the reason it cannot be analysed."""
    try:
        with open(csv_path, newline="", encoding="utf-8-sig") as handle:  # -sig: a BOM must not rename a column
            reader = csv.DictReader(handle)
            missing = missing_required_columns(reader.fieldnames)
            if missing:
                return f"the CSV is missing required columns: {', '.join(missing)}"
            rows = list(reader)
    except UnicodeDecodeError:
        return "the file is not valid UTF-8 text"
    except csv.Error as exc:
        return f"the file could not be read as CSV ({exc})"
    except OSError as exc:
        return f"could not read the file ({exc.strerror or type(exc).__name__})"
    if not rows:
        return "the CSV has a header row but no data rows"
    return rows


def _export(result, export_path: Path) -> int:
    export_rows = to_export_rows(result)
    try:
        with open(export_path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
            writer.writeheader()
            writer.writerows(export_rows)
    except OSError as exc:
        return _fail(f"could not save the results to {export_path} ({exc.strerror or type(exc).__name__})")
    print(f"Se exportaron {len(export_rows)} métricas a {export_path}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python analyze.py <path-to-csv>", file=sys.stderr)
        return 2

    csv_path = Path(argv[1])
    if not csv_path.is_file():
        return _fail(f"file not found: {csv_path}")

    rows = _read(csv_path)
    if isinstance(rows, str):
        return _fail(rows)

    result = analyze(rows, source_name=csv_path.name)
    print(format_report(result))

    if result.valid_records == 0:
        print("Error: there is not one valid record in the file, so there is nothing to export.", file=sys.stderr)
        return 3

    try:
        answer = input("¿Deseas exportar los resultados a CSV? [s / n]: ").strip().lower()
    except EOFError:  # run from a pipe, a cron job or a CI: nobody to ask
        print("\nExportación omitida (no hay entrada interactiva).")
        return 0
    if answer == "s":
        return _export(result, csv_path.parent / "results.csv")
    print("Exportación omitida.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        raise SystemExit(130) from None
