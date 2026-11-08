"""Checks the two least-privilege roles of ``sql/002_roles.sql`` against a real database, and can then run the pipeline with them.

    python data/pipelines/verify_roles.py                 # checks the permissions; writes NOTHING
    python data/pipelines/verify_roles.py --run           # ...and, if all is right, runs the pipeline with the two roles
    python data/pipelines/verify_roles.py --write-env     # ...and, if all is right, saves the two URLs in services/api/.env
    python data/pipelines/verify_roles.py --run --environment development --week-start 2026-10-26

The database is the one of ``DATABASE_URL`` (the environment or ``services/api/.env``). The two role URLs are BUILT from it,
changing only the user (``pipeline_reader`` / ``pipeline_writer``, keeping a Supabase ``.PROJECT_ID`` suffix if there is one) and
the password, which are asked for WITHOUT showing them. Nothing is printed or stored: the passwords live in this process only.

``--write-env`` appends TELEMETRY_DATABASE_URL (the reader) and REPORTING_DATABASE_URL (the writer) to the env file the pipeline
already reads (``services/api/.env``, or PIPELINE_ENV_FILE), so the plain command ``python data/pipelines/pipeline.py`` uses the roles
from then on. It only writes when every check passed; it refuses if the file is not ignored by git (a password must never reach a
commit) or if either variable is already there (it never overwrites); and it never prints the URLs.

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
import re
import subprocess
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError

from data.pipelines.weekly_office_performance import storage

REPO_ROOT = Path(__file__).resolve().parents[2]
READER, WRITER = "pipeline_reader", "pipeline_writer"
ENV_KEYS = ("TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL")  # the reader's URL, the writer's URL
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


class EnvFileError(RuntimeError):
    """The env file cannot be written safely; its text says why."""


def env_file_path() -> Path:
    """The file the pipeline reads its environment from (the same rule as ``storage.load_api_env``)."""
    return Path(os.environ.get("PIPELINE_ENV_FILE") or REPO_ROOT / "services" / "api" / ".env")


def is_git_ignored(path: Path) -> bool:
    """True only if git says the file is ignored. Any doubt (no git, not a repository) is False: a secret must not be written there."""
    try:
        return subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=REPO_ROOT, capture_output=True, timeout=20, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def write_env(path: Path, urls: dict[str, str]) -> None:
    """Append ``urls`` (variable -> URL) to the env file, single-quoted so no character of a password is read as anything else.
    Refuses, leaving the file as it was, if it is not ignored by git or if a variable is already in it."""
    if not is_git_ignored(path):
        raise EnvFileError(f"{path} is not ignored by git: not writing passwords there")
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    present = [key for key in urls if re.search(rf"^\s*(export\s+)?{key}\s*=", current, re.MULTILINE)]
    if present:
        raise EnvFileError(f"{', '.join(present)} already in {path}: not overwriting. Edit the file by hand or remove those lines first")
    lines = ["# Added by data/pipelines/verify_roles.py: least-privilege roles of the weekly pipeline (reader / writer)"]
    lines += [f"{key}='{url}'" for key, url in urls.items()]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(("\n" if current and not current.endswith("\n") else "") + "\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the two least-privilege roles against the database of DATABASE_URL.")
    parser.add_argument("--run", action="store_true", help="if every check passes, run the pipeline with the two roles")
    parser.add_argument("--write-env", action="store_true", help="if every check passes, save the two role URLs in services/api/.env (never shown)")
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
    if args.write_env:
        path = env_file_path()
        try:
            write_env(path, {ENV_KEYS[0]: role_url(admin_url, READER, reader_password).render_as_string(hide_password=False),
                             ENV_KEYS[1]: role_url(admin_url, WRITER, writer_password).render_as_string(hide_password=False)})
        except EnvFileError as error:
            print(f"\nNot saved: {error}", file=sys.stderr)
            return 1
        print(f"\nSaved {ENV_KEYS[0]} and {ENV_KEYS[1]} in {path} (the values are not shown).")
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
