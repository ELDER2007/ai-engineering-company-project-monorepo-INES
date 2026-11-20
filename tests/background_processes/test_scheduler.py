"""The trigger of the nightly job (ticket DEV-53): the dedicated scheduler container, its crontab, and that nothing of the other projects changes.

What the evaluation looks at: "the trigger is configured and the cron expression documented in the PR". The PR is text; the repository
keeps the same words in ``infra/scheduler/README.md``, and these tests keep that text and the files that it talks about from drifting apart.

Run:  python -m pytest tests/background_processes/test_scheduler.py
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
SCHEDULER = REPO / "infra" / "scheduler"
CRONTAB = (SCHEDULER / "crontab").read_text(encoding="utf-8")
README = (SCHEDULER / "README.md").read_text(encoding="utf-8")
DOCKERFILE = (SCHEDULER / "Dockerfile").read_text(encoding="utf-8")
COMPOSE = yaml.safe_load((REPO / "docker-compose.yml").read_text(encoding="utf-8"))
EXPRESSION = "0 2 * * *"


def active_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


# ---------------------------------------------------------------- the crontab and its expression


def test_the_crontab_has_exactly_one_job_every_day_at_two_utc_that_runs_the_script():
    (line,) = active_lines(CRONTAB)
    assert line == f"{EXPRESSION} cd /app && python scripts/nightly_export.py"


def test_the_expression_fires_every_day_at_0200_utc():
    """Asked to Prefect's own calendar, so it is the cron library that says when it fires, not this test."""
    from prefect.server.schemas.schedules import CronSchedule

    start = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)
    fires = asyncio.run(CronSchedule(cron=EXPRESSION, timezone="UTC").get_dates(n=4, start=start))
    assert [f.astimezone(timezone.utc) for f in fires] == [datetime(2026, 11, d, 2, 0, tzinfo=timezone.utc) for d in (9, 10, 11, 12)]


def test_it_is_not_the_schedule_of_the_pipeline_monday_and_thursday_at_0500_utc():
    assert EXPRESSION not in ("0 5 * * 1", "0 5 * * 4")
    assert "0 5 * * 1" not in " ".join(active_lines(CRONTAB)) and "Monday and Thursday at 05:00 UTC" in README


# ---------------------------------------------------------------- the decision is written down, with its reasons


def test_the_readme_documents_the_expression_the_hour_and_why():
    assert f"`{EXPRESSION}`" in README or EXPRESSION in README
    assert "02:00 UTC" in README and "TZ=UTC" in README
    assert all(word in README for word in ("Why 02:00", "offline", "traffic"))


def test_the_readme_justifies_the_container_and_rules_out_the_scheduler_inside_fastapi():
    assert "Dedicated scheduler container" in README and "**Chosen.**" in README
    assert all(name in README for name in ("APScheduler", "@repeat_every", "lifespan"))
    assert "Ruled out" in README and "first acceptance criterion" in README
    assert "crontab" in README and "0 2 * * *  cd /path/to/repo" in README  # the alternative, one line, for whoever does not want the container


def test_the_readme_says_how_to_run_a_given_day_and_that_a_missed_night_is_not_caught_up():
    assert "TARGET_DATE=2026-10-30" in README and "not caught up by itself" in README


def test_the_crontab_comments_say_what_the_job_does_and_why_that_hour():
    assert "02:00 UTC" in CRONTAB and "TARGET_DATE" in CRONTAB and "offline" in CRONTAB


# ---------------------------------------------------------------- docker-compose.yml: one more service, and nothing else changed


def test_the_scheduler_is_a_service_of_its_own_off_by_default_that_does_not_depend_on_the_api():
    scheduler = COMPOSE["services"]["scheduler"]
    assert scheduler["profiles"] == ["scheduler"]  # a plain `docker compose up` does not start it
    assert scheduler["build"] == {"context": ".", "dockerfile": "infra/scheduler/Dockerfile"}
    assert "depends_on" not in scheduler and "ports" not in scheduler and "command" not in scheduler
    assert scheduler["environment"]["TZ"] == "UTC" and scheduler["environment"]["NIGHTLY_REQUIRE_DATABASE_URL"] == "1"
    assert {"path": ".env", "required": False} in scheduler["env_file"]
    assert "./data/raw:/app/data/raw" in scheduler["volumes"] and scheduler["networks"] == ["nexova-net"]


def test_the_uis_are_what_they_were_in_main_and_the_api_only_gained_the_one_build_context_it_needs():
    """Respecting each project: ``uis`` is untouched, and ``api`` differs from main in exactly one line: the named context ``data`` that its reporting module imports."""
    import copy

    if shutil.which("git") is None:
        pytest.skip("needs git")
    shown = subprocess.run(["git", "show", "origin/main:docker-compose.yml"], cwd=REPO, capture_output=True, text=True, check=False)
    if shown.returncode != 0:
        pytest.skip("origin/main is not available here")
    before = yaml.safe_load(shown.stdout)
    expected_api = copy.deepcopy(before["services"]["api"])
    expected_api["build"]["additional_contexts"]["data"] = "./data"
    assert COMPOSE["services"]["api"] == expected_api  # nothing else of the api service changed
    assert COMPOSE["services"]["uis"] == before["services"]["uis"]
    assert COMPOSE["networks"] == before["networks"] and set(COMPOSE["services"]) - set(before["services"]) == {"scheduler"}


def test_the_api_image_carries_the_code_of_the_pipeline_it_imports_and_never_the_data_folders():
    """Without data/pipelines the API did not start in Docker (ModuleNotFoundError: No module named 'data'). Runtime output must not be baked in."""
    dockerfile = (REPO / "services" / "Dockerfile").read_text(encoding="utf-8")
    sources = [line.split()[2] for line in dockerfile.splitlines() if line.startswith("COPY --from=data")]  # COPY --from=data <source> <destination>
    assert sources == ["__init__.py", "pipelines", "process"]  # the code, and nothing else of ./data (no raw, no eval, no .local)
    requirements = (REPO / "services" / "api" / "requirements.txt").read_text(encoding="utf-8")
    assert "prefect>=3.9.2" in requirements  # an older Prefect breaks with the newest FastAPI when it starts its server


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs the docker CLI")
def test_compose_starts_only_api_and_uis_unless_the_profile_is_asked_for():
    def services(*profile):
        out = subprocess.run(["docker", "compose", *profile, "config", "--services"], cwd=REPO, capture_output=True, text=True, timeout=60, check=False)
        assert out.returncode == 0, out.stderr[-400:]
        return set(out.stdout.split())

    assert services() == {"api", "uis"}
    assert services("--profile", "scheduler") == {"api", "uis", "scheduler"}


# ---------------------------------------------------------------- the image: only what the job needs, and no secrets


def test_the_image_runs_supercronic_over_the_crontab_and_nothing_else():
    assert DOCKERFILE.splitlines()[-1] == 'CMD ["supercronic", "-passthrough-logs", "/app/infra/scheduler/crontab"]'
    assert "FROM python:3.12-slim" in DOCKERFILE and "TZ=UTC" in DOCKERFILE
    instructions = "\n".join(line for line in DOCKERFILE.splitlines() if not line.lstrip().startswith("#"))  # the comments may SAY "FastAPI"
    assert not re.search(r"uvicorn|fastapi|EXPOSE", instructions, re.IGNORECASE)  # it serves nothing: no port, no API


def test_supercronic_is_pinned_and_checked_against_the_published_sha256():
    assert re.search(r"SUPERCRONIC_VERSION=v\d+\.\d+\.\d+", DOCKERFILE)
    assert len(re.findall(r"SUPERCRONIC_SHA256_(?:AMD64|ARM64)=[0-9a-f]{64}", DOCKERFILE)) == 2
    assert 'sha256sum -c -' in DOCKERFILE


def test_the_image_copies_only_what_the_job_needs_and_never_the_env_file():
    copies = [line.split()[1] for line in DOCKERFILE.splitlines() if line.startswith("COPY ")]
    assert set(copies) == {"packages/shared/incidents_analyzer", "packages/shared/incidents", "services/api/requirements.txt", "services/api/core",
                           "services/api/job_runner", "infra/scheduler/constraints.txt", "data/__init__.py", "data/pipelines", "data/process", "scripts/nightly_export.py", "infra/scheduler/crontab"}
    assert not any(c in (".", "services/api", "services", "data") or c.endswith(".env") for c in copies)  # no whole folder: services/api/.env lives in services/api


def test_every_file_the_job_imports_is_in_the_image():
    """The script and the pipeline it launches import these folders: if one were left out, the container would fail the first night."""
    imported = {"core", "job_runner"}  # from the script, via services/api
    copied = {c for c in re.findall(r"COPY (\S+)", DOCKERFILE)}
    for folder in imported:
        assert f"services/api/{folder}" in copied
    assert {"data/pipelines", "data/process", "data/__init__.py"} <= copied


def test_the_versions_that_work_together_are_pinned_for_this_image_only_and_the_reason_is_written():
    constraints = (SCHEDULER / "constraints.txt").read_text(encoding="utf-8")
    assert active_lines(constraints) == ["prefect>=3.9.2", "fastapi<0.151"]
    assert "min_items" in constraints and "not touched" in constraints  # why, and that the API is not affected
    assert "-c /app/infra/scheduler/constraints.txt" in DOCKERFILE


def test_the_build_ignores_secrets_and_the_local_data_of_whoever_builds():
    ignored = (SCHEDULER / "Dockerfile.dockerignore").read_text(encoding="utf-8")
    assert "**/.env" in ignored and "!**/.env.example" in ignored and "data/raw" in ignored and ".git" in ignored


def test_a_container_without_a_database_refuses_to_run_instead_of_using_a_throw_away_file(monkeypatch, capsys, script):
    monkeypatch.setenv("NIGHTLY_REQUIRE_DATABASE_URL", "1")
    monkeypatch.setenv("DATABASE_URL", "")
    assert script.main([]) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_with_a_database_the_requirement_changes_nothing(monkeypatch, tmp_path, script):
    monkeypatch.setenv("NIGHTLY_REQUIRE_DATABASE_URL", "1")
    monkeypatch.setenv("TARGET_DATE", "2026-10-30")
    monkeypatch.setenv("NIGHTLY_PIPELINE_COMMAND", "python -c pass")
    from data.pipelines.weekly_office_performance.storage import telemetry_events
    from job_runner import database

    telemetry_events.create(database.build_engine())
    assert script.main([]) == 0
