"""CLI: ``python -m data.pipelines.weekly_office_performance [--week-start YYYY-MM-DD] [--seed]``.

Run it from the repository root. ``--seed`` first loads the demo telemetry (local dev only).
"""

from __future__ import annotations

import argparse
from datetime import date

from data.pipelines.weekly_office_performance import storage
from data.pipelines.weekly_office_performance.flow import weekly_office_performance_flow


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", type=date.fromisoformat, default=None)
    parser.add_argument("--seed", action="store_true", help="load demo telemetry_events first (local dev)")
    args = parser.parse_args()

    source = storage.build_engine(storage.database_url("TELEMETRY_DATABASE_URL"))
    if args.seed:
        from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

        print(f"seeded {seed_telemetry(source)} telemetry events")
    summary = weekly_office_performance_flow(week_start=args.week_start, trigger="manual", source_engine=source)
    print(summary)


if __name__ == "__main__":
    main()
