#!/usr/bin/env python3
"""Start the API on the pipeline's DEMO database, so that the ``/reporting`` endpoints show numbers. One command, from any folder:

    python data/pipelines/serve_demo.py              # the API on http://127.0.0.1:8000
    python data/pipelines/serve_demo.py --port 8010
    python data/pipelines/serve_demo.py --check      # only says what it would do; starts nothing, writes nothing

On a clean clone the API starts but its report is empty (``404 No week has been computed yet``): its database has no telemetry events, so the pipeline has
nothing to compute. This script gives it some, WITHOUT touching any real database:

1. If the demo database (``data/.local/demo.sqlite``, or ``PIPELINE_DEMO_DB``) has no computed week, it runs ``python data/pipelines/pipeline.py --demo``: a throw-away
   file with example events, the week of 2026-10-26 computed by the real pipeline.
2. It starts ``uvicorn main:app`` from ``services/api`` with DATABASE_URL, REPORTING_DATABASE_URL and TELEMETRY_DATABASE_URL all pointing at that file, so the API
   cannot reach any other database from this process, whatever ``services/api/.env`` says.
3. It prints how to log in. The demo user is created by the API only if it has no users yet (``AUTH_INITIAL_EMAIL`` / ``AUTH_INITIAL_PASSWORD``); if you already
   have an account, use it. Set those two variables yourself to choose another one.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:  # `python data/pipelines/serve_demo.py`: make `data.` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import os
import subprocess
from collections.abc import Mapping

from sqlalchemy import text

from data.pipelines.weekly_office_performance import storage

REPO = Path(__file__).resolve().parents[2]
API = REPO / "services" / "api"
PIPELINE = REPO / "data" / "pipelines" / "pipeline.py"
DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo-password-123"
DEMO_WEEK = "2026-10-26"


def has_computed_week(url: str) -> bool:
    """Does the demo database already hold a computed week? (False if it does not exist yet: nothing here creates the demo events.)"""
    main_file = Path(url.removeprefix("sqlite:///"))
    if not (main_file.exists() and Path(f"{main_file}.reporting").exists()):
        return False  # connecting would CREATE those files (SQLite does), so ask the filesystem first: --check must write nothing
    engine = storage.build_engine(url)
    try:
        with engine.connect() as connection:
            return bool(connection.execute(text("select count(*) from reporting.weekly_office_program_performance")).scalar())
    except Exception:  # noqa: BLE001 - no file, no table: there is no computed week
        return False
    finally:
        engine.dispose()


def build_environment(base: Mapping[str, str], demo_url: str) -> dict[str, str]:
    """The environment of the API: every database variable points at the demo file. A user-chosen demo login is kept."""
    env = dict(base)
    for name in ("DATABASE_URL", "REPORTING_DATABASE_URL", "TELEMETRY_DATABASE_URL"):
        env[name] = demo_url
    env.setdefault("AUTH_INITIAL_EMAIL", DEMO_EMAIL)
    env.setdefault("AUTH_INITIAL_PASSWORD", DEMO_PASSWORD)
    return env


def banner(env: Mapping[str, str], host: str, port: int) -> str:
    email, password = env.get("AUTH_INITIAL_EMAIL", ""), env.get("AUTH_INITIAL_PASSWORD", "")
    login = (f"  log in (Swagger: Authorize): {email} / {password}\n  (the API creates that user only if it has no users yet; otherwise use one of your own)\n"
             if email and password else "  use an account that already exists (no demo login is set)\n")
    return (f"\nDEMO API on http://{host}:{port}/docs   (demo data of the week {DEMO_WEEK}; no real database is used)\n{login}"
            f"  then:  GET /reporting/weekly-office-program-performance   -> five rows\n"
            f"         GET /reporting/pipeline-runs/latest                -> the run that computed them\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the API on the pipeline's demo database, so /reporting shows numbers.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--check", action="store_true", help="only say what would be done; start nothing and write nothing")
    args = parser.parse_args(argv)

    demo_url = storage.demo_url()
    env = build_environment(os.environ, demo_url)
    demo_file = demo_url.removeprefix("sqlite:///")
    if args.check:
        state = "has a computed week" if has_computed_week(demo_url) else "has none: it would run the pipeline with --demo first"
        print(f"demo database: {demo_file} ({state})")
        print(f"it would start: uvicorn main:app --host {args.host} --port {args.port}   (from {API})")
        print("every database variable of the API would point at the demo file; nothing else would be touched.")
        return 0

    if not has_computed_week(demo_url):
        print("Computing the demo week with the real pipeline (a throw-away database, a few seconds)...", flush=True)
        done = subprocess.run([sys.executable, str(PIPELINE), "--demo"], cwd=REPO, env=dict(os.environ), check=False)
        if done.returncode != 0 or not has_computed_week(demo_url):
            print("error: the demo run did not leave a computed week: see the output above", file=sys.stderr)
            return 1
    print(banner(env, args.host, args.port), flush=True)
    os.chdir(API)
    os.execvpe(sys.executable, [sys.executable, "-m", "uvicorn", "main:app", "--host", args.host, "--port", str(args.port)], env)  # replaces this process
    return 0  # unreachable


if __name__ == "__main__":
    sys.exit(main())
