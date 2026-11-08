"""Checks the two least-privilege roles of ``sql/002_roles.sql`` against a real database, and can then run the pipeline with them.

    python data/pipelines/verify_roles.py                 # checks the permissions; writes NOTHING
    python data/pipelines/verify_roles.py --run           # ...and, if all is right, runs the pipeline with the two roles
    python data/pipelines/verify_roles.py --run --environment development --week-start 2026-10-26

The database is the one of ``DATABASE_URL`` (the environment or ``services/api/.env``). The two role URLs are BUILT from it,
changing only the user (``pipeline_reader`` / ``pipeline_writer``, keeping a Supabase ``.PROJECT_ID`` suffix if there is one) and
the password, which are asked for WITHOUT showing them. Nothing is printed or stored: the passwords live in this process only.

Every check is read-only: the "can it write?" checks use ``delete ... where false``, which deletes nothing even if it is allowed.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:  # `python data/pipelines/verify_roles.py`: make `data.` importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import argparse
import getpass
import os
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from data.pipelines.weekly_office_performance import storage

READER, WRITER = "pipeline_reader", "pipeline_writer"
TELEMETRY = "public.telemetry_events"
REPORTING_TABLES = ("reporting.pipeline_runs", "reporting.weekly_office_program_performance")


@dataclass(frozen=True)
class Check:
    ok: bool
    text: str

    def __str__(self) -> str:
        return f"{'OK   ' if self.ok else 'FALLA'} {self.text}"


def role_url(admin_url: str | URL, role: str, password: str) -> URL:
    """The URL of ``role``: the administrator's, with another user and password. A Supabase pooler user is ``name.PROJECT_ID``: the
    ``.PROJECT_ID`` is kept. The password is passed as data, so any character in it is fine."""
    url = make_url(admin_url)
    suffix = url.username.split(".", 1)[1] if url.username and "." in url.username else None
    return url.set(username=f"{role}.{suffix}" if suffix else role, password=password)


def _allowed(engine, statement: str) -> bool | None:
    """True if the statement runs, False if the database refuses it for lack of privilege, None for any other error."""
    try:
        with engine.connect() as connection:
            result = connection.execute(text(statement))
            if result.returns_rows:
                result.all()
            connection.rollback()  # whatever it was, nothing is kept
        return True
    except DBAPIError as error:
        return False if getattr(error.orig, "pgcode", None) == "42501" else None  # 42501 = insufficient_privilege


def check_roles(admin_url: str | URL, reader_password: str, writer_password: str) -> list[Check]:
    """Everything the roles must and must not be able to do. Read-only."""
    reader = create_engine(role_url(admin_url, READER, reader_password), pool_pre_ping=True)
    writer = create_engine(role_url(admin_url, WRITER, writer_password), pool_pre_ping=True)
    checks: list[Check] = []
    try:
        try:
            with reader.connect() as connection:
                events = connection.execute(text(f"select count(*) from {TELEMETRY}")).scalar()
                rls_on = connection.execute(text(f"select relrowsecurity from pg_class where oid = '{TELEMETRY}'::regclass")).scalar()
                policy = connection.execute(text(
                    "select count(*) from pg_policies where tablename = 'telemetry_events' and :role = any(roles::text[]) and cmd in ('SELECT', 'ALL')"),
                    {"role": READER}).scalar()
            checks.append(Check(True, f"{READER} reads the telemetry: {events} events in the table"))
            checks.append(Check(not rls_on or policy > 0, f"row level security is {'ON' if rls_on else 'off'} for the telemetry"
                                + (f" and {READER} has a policy to read it" if rls_on and policy else "")
                                + ("" if not rls_on or policy else f": WITHOUT a policy {READER} reads 0 rows and no error. Run the create policy line of 002_roles.sql")))
        except DBAPIError as error:
            checks.append(Check(False, f"{READER} could not connect or read the telemetry: {str(error.orig).strip().splitlines()[0]}"))
        checks.append(Check(_allowed(reader, f"delete from {TELEMETRY} where false") is False, f"{READER} CANNOT write in the telemetry"))
        checks.append(Check(_allowed(reader, f"select count(*) from {REPORTING_TABLES[0]}") is False, f"{READER} cannot see the reporting tables"))
        for table in REPORTING_TABLES:
            checks.append(Check(_allowed(writer, f"select count(*) from {table}") is True, f"{WRITER} reads {table}"))
            checks.append(Check(_allowed(writer, f"delete from {table} where false") is True, f"{WRITER} can write in {table}"))
        checks.append(Check(_allowed(writer, f"select count(*) from {TELEMETRY}") is False, f"{WRITER} CANNOT read the telemetry"))
        checks.append(Check(_allowed(writer, f"delete from {TELEMETRY} where false") is False, f"{WRITER} CANNOT write in the telemetry"))
    finally:
        reader.dispose()
        writer.dispose()
    return checks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the two least-privilege roles against the database of DATABASE_URL.")
    parser.add_argument("--run", action="store_true", help="if every check passes, run the pipeline with the two roles")
    parser.add_argument("--environment", default=None, help="telemetry environment for --run (default: the pipeline's)")
    parser.add_argument("--week-start", default=None, help="Monday of the week for --run, YYYY-MM-DD (default: the last complete week)")
    args = parser.parse_args(argv)

    admin_url = storage.database_url("DATABASE_URL")
    if admin_url.startswith("sqlite"):
        print("DATABASE_URL does not point to a PostgreSQL database: nothing to check.", file=sys.stderr)
        return 2
    reader_password = getpass.getpass(f"Password of {READER} (not shown): ")
    writer_password = getpass.getpass(f"Password of {WRITER} (not shown): ")

    checks = check_roles(admin_url, reader_password, writer_password)
    for check in checks:
        print(check)
    if not all(c.ok for c in checks):
        print("\nSome checks FAILED: nothing was run. Nothing was written to the database either.")
        return 1
    print("\nAll the checks passed: the roles can do what they need and nothing else.")
    if not args.run:
        return 0

    # In this process only (never exported, never printed): the pipeline reads with the reader and writes with the writer.
    os.environ["TELEMETRY_DATABASE_URL"] = role_url(admin_url, READER, reader_password).render_as_string(hide_password=False)
    os.environ["REPORTING_DATABASE_URL"] = role_url(admin_url, WRITER, writer_password).render_as_string(hide_password=False)
    from data.pipelines import pipeline

    options: list[str] = []
    if args.environment:
        options += ["--environment", args.environment]
    if args.week_start:
        options += ["--week-start", args.week_start]
    print("\nRunning the pipeline with the two roles...")
    return pipeline.main(options)


if __name__ == "__main__":
    sys.exit(main())
