"""Registers the weekly pipeline as a Prefect DEPLOYMENT with its two crons (design, section 4.6).

    python data/pipelines/deploy.py --dry-run                      # prints the plan, needs no server
    python data/pipelines/deploy.py --work-pool nexova-reporting   # registers it in the Prefect server of the current profile
    python data/pipelines/deploy.py --serve                        # development: runs the schedules from this process

One deployment, two schedules, both in UTC and both on the last COMPLETE week (``week_start`` is left empty):

* Monday 05:00 (``0 5 * * 1``): the scheduled run, ready before the leadership reads it at 06:00.
* Thursday 05:00 (``0 5 * * 4``): the correction run, with ``refresh=True`` so it ignores the one-hour cache and absorbs
  the late events of the same week (annex of the design, I-3).

A manual run (``POST /reporting/pipeline-runs`` or ``--week-start`` on the command line) does not need a deployment.
After registering, start a worker for the pool: ``prefect worker start --pool <work-pool>``.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:  # `python data/pipelines/deploy.py`: make `data.` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import json
from typing import Any

from prefect.schedules import Cron

from data.pipelines import pipeline

DEPLOYMENT_NAME = "weekly-office-performance"
DEFAULT_WORK_POOL = "nexova-reporting"
TIMEZONE = "UTC"
ENTRYPOINT = "data/pipelines/pipeline.py:weekly_office_performance_flow"
REPO_ROOT = Path(__file__).resolve().parents[2]

MONDAY = "0 5 * * 1"
THURSDAY = "0 5 * * 4"


def build_schedules() -> list[Any]:
    return [
        Cron(MONDAY, timezone=TIMEZONE, slug="monday-scheduled", parameters={"trigger": "scheduled", "refresh": False}),
        Cron(THURSDAY, timezone=TIMEZONE, slug="thursday-correction", parameters={"trigger": "scheduled", "refresh": True}),
    ]


def job_variables(secret_blocks: bool) -> dict[str, Any]:
    """Environment of the runs. With the Secret blocks on, the runs read their credentials from the blocks."""
    return {"env": {"PIPELINE_SECRET_BLOCKS": "1"}} if secret_blocks else {}


def plan(work_pool: str, secret_blocks: bool) -> dict[str, Any]:
    """What would be registered, as plain data (what ``--dry-run`` prints and what the tests check)."""
    return {
        "name": f"{pipeline.FLOW_NAME}/{DEPLOYMENT_NAME}",
        "entrypoint": ENTRYPOINT,
        "work_pool": work_pool,
        "job_variables": job_variables(secret_blocks),
        "schedules": [
            {"slug": s.slug, "cron": s.cron, "timezone": s.timezone, "parameters": s.parameters} for s in build_schedules()
        ],
    }


def register(work_pool: str, secret_blocks: bool = False) -> str:
    """Create or update the deployment in the Prefect server of the current profile. Returns its id."""
    flow = pipeline.weekly_office_performance_flow.from_source(source=str(REPO_ROOT), entrypoint=ENTRYPOINT)
    return str(
        flow.deploy(
            name=DEPLOYMENT_NAME,
            work_pool_name=work_pool,
            schedules=build_schedules(),
            job_variables=job_variables(secret_blocks) or None,
            description="Weekly report of performance by office and programme: Monday run and Thursday correction (UTC).",
            tags=["reporting", "weekly"],
            build=False,
            push=False,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Register the weekly pipeline as a Prefect deployment with its two crons.")
    parser.add_argument("--work-pool", default=DEFAULT_WORK_POOL, help=f"work pool of type 'process' (default: {DEFAULT_WORK_POOL})")
    parser.add_argument("--secret-blocks", action="store_true", help="the runs read their credentials from the Prefect Secret blocks")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print what would be registered and exit; needs no server")
    mode.add_argument("--serve", action="store_true", help="development: run the schedules from this process instead of registering")
    args = parser.parse_args(argv)

    if args.dry_run:
        print(json.dumps(plan(args.work_pool, args.secret_blocks), indent=2))
        return 0
    if args.serve:
        pipeline.weekly_office_performance_flow.serve(name=DEPLOYMENT_NAME, schedules=build_schedules(), tags=["reporting", "weekly"])
        return 0
    deployment_id = register(args.work_pool, args.secret_blocks)
    print(f"deployment registered: {pipeline.FLOW_NAME}/{DEPLOYMENT_NAME} ({deployment_id}) in work pool '{args.work_pool}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
