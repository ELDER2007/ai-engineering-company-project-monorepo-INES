"""The command line still works after the split into subflows.

``python data/pipelines/pipeline.py`` runs the whole ETL without errors, its entrypoint (``__main__``) is the one of part 2, and the
command documented in part 2 is still valid. These tests run the REAL command, in a subprocess, exactly as a person would; and they
parse every command the documentation shows, so the documentation cannot drift away from the program.

Run:  python -m pytest tests/pipelines/test_cli.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from data.pipelines import pipeline

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "data" / "pipelines" / "pipeline.py"
PHASE_SUBFLOWS = ["extract-kpi-events", "transform-weekly-kpis", "load-weekly-office-program-performance"]
OPTIONAL_SUBFLOWS = ["window-liveness-count", "raw-events-snapshot", "validation-report"]
KPI_TASKS = ["calculate_total_material_cost", "count_kits_delivered", "count_shortage_events", "count_cost_variance_events"]
DOCS = [
    REPO / "data" / "pipelines" / "PIPELINE_DESIGN.md",
    REPO / "data" / "pipelines" / "README.md",
    REPO / "data" / "pipelines" / "README.es.md",
    REPO / "data" / "pipelines" / "weekly_office_performance" / "README.md",
    SCRIPT,
]


def clean_environment(tmp_path: Path, **extra) -> dict[str, str]:
    """A fresh checkout: no database configured, no local telemetry. Retries are NOT switched off: this is the real program."""
    env = {k: v for k, v in os.environ.items()
           if k not in {"DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL", "PIPELINE_ENVIRONMENT", "PIPELINE_RETRIES"}}
    env.update(PIPELINE_ENV_FILE=str(tmp_path / "no.env"), PIPELINE_LOCAL_DB=str(tmp_path / "no-app.sqlite"),
               PIPELINE_DEMO_DB=str(tmp_path / "demo.sqlite"), PIPELINE_DATA_DIR=str(tmp_path / "data"),
               PREFECT_LOCAL_STORAGE_PATH=str(tmp_path / "prefect-results"),  # the cache of the test run, not the user's ~/.prefect
               **extra)
    return env


def run_command(args: list[str], env: dict[str, str], cwd: Path = REPO) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


def order_of(text: str, names: list[str]) -> list[int]:
    return [text.index(f"for flow '{name}'") for name in names]


# ---------------------------------------------------------------- the real command, with no arguments


def test_the_exact_command_runs_the_whole_etl_without_errors(tmp_path):
    """python data/pipelines/pipeline.py"""
    out = run_command([sys.executable, "data/pipelines/pipeline.py"], clean_environment(tmp_path))
    assert out.returncode == 0, out.stderr[-1500:]
    assert "state='Completed'" in out.stdout and "error=None" in out.stdout


def test_the_command_runs_the_subflows_of_the_new_structure_in_order_extract_transform_load(tmp_path):
    out = run_command([sys.executable, "data/pipelines/pipeline.py"], clean_environment(tmp_path))
    assert out.returncode == 0, out.stderr[-1500:]
    positions = order_of(out.stderr, PHASE_SUBFLOWS)
    assert positions == sorted(positions), "the phases did not run in order"
    for name in OPTIONAL_SUBFLOWS:
        assert f"for flow '{name}'" in out.stderr, name
    for task in KPI_TASKS:  # one task per KPI ran inside the transformation
        assert re.search(rf"Task run '{task}-[0-9a-f]+' - Finished in state (Completed|Cached)", out.stderr), task


def test_the_command_leaves_the_validation_report_with_the_four_kpis_of_every_office_and_programme(tmp_path):
    out = run_command([sys.executable, "data/pipelines/pipeline.py"], clean_environment(tmp_path))
    assert out.returncode == 0, out.stderr[-1500:]
    (report_path,) = (tmp_path / "data" / "eval").glob("run_*.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["state"] == "Completed" and report["reconciliation"]["ok"]
    assert len(report["kpis"]) == 5
    assert set(report["kpis"][0]) == {"office", "programme_id", "currency", "total_material_cost", "kits_delivered_count",
                                      "shortage_events_count", "cost_variance_events_count"}
    assert sum(k["kits_delivered_count"] for k in report["kpis"]) == 7  # the demo week: 7 deliveries, 2 shortages, 1 cost variance
    assert sum(k["shortage_events_count"] for k in report["kpis"]) == 2
    assert sum(k["cost_variance_events_count"] for k in report["kpis"]) == 1


def test_the_command_runs_from_any_folder(tmp_path):
    elsewhere = tmp_path / "somewhere" / "else"
    elsewhere.mkdir(parents=True)
    out = run_command([sys.executable, str(SCRIPT)], clean_environment(tmp_path), cwd=elsewhere)
    assert out.returncode == 0 and "state='Completed'" in out.stdout, out.stderr[-1500:]


def test_the_module_form_of_the_command_works_too(tmp_path):
    out = run_command([sys.executable, "-m", "data.pipelines.pipeline"], clean_environment(tmp_path))
    assert out.returncode == 0 and "state='Completed'" in out.stdout, out.stderr[-1500:]


def test_a_failure_still_ends_with_exit_code_1_and_says_why(tmp_path):
    """With a database configured that has no telemetry the run fails, and the program says so: exit code 1, never the demo."""
    env = clean_environment(tmp_path, DATABASE_URL=f"sqlite:///{tmp_path / 'configured-but-empty.sqlite'}")
    out = run_command([sys.executable, "data/pipelines/pipeline.py", "--week-start", "2026-10-26"], env)
    assert out.returncode == 1 and "FAILED" in out.stderr and "DEMO" not in out.stderr


# ---------------------------------------------------------------- the entrypoint is the one of part 2


def test_the_entrypoint_is_still_pipeline_py_with_a_main_block_that_exits_with_the_result_of_main():
    assert SCRIPT.name == "pipeline.py" and SCRIPT.parent.name == "pipelines"
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    guard = next(n for n in tree.body if isinstance(n, ast.If) and "__main__" in ast.dump(n.test) and "__package__" not in ast.dump(n.test))
    assert "sys.exit(main())" in ast.unparse(guard)


def test_main_still_takes_an_argument_list_and_returns_an_exit_code():
    import inspect

    signature = inspect.signature(pipeline.main)
    assert list(signature.parameters) == ["argv"] and "int" in str(signature.return_annotation)


# ---------------------------------------------------------------- the documentation of the command is still valid


def documented_commands() -> set[tuple[str, ...]]:
    """Every runnable command the documentation shows (synopsis lines with [options], <placeholders> or ... are not commands)."""
    commands: set[tuple[str, ...]] = set()
    for doc in DOCS:
        text = re.sub(r"[ \t]#[^\n]*", "", doc.read_text(encoding="utf-8"))  # a comment after a command is prose, not part of a command
        for match in re.finditer(r"python (?:-m data\.pipelines\.pipeline|data/pipelines/pipeline\.py)([^\n`]*)", text):
            tail = match.group(1).split("#")[0].strip()
            if any(token in tail for token in ("[", "<", "...", "|", "(")):
                continue
            commands.add(tuple(shlex.split(tail)))
    return commands


def test_the_documentation_shows_the_command_of_part_2():
    commands = documented_commands()
    assert () in commands  # `python data/pipelines/pipeline.py` with no arguments
    assert ("--week-start", "2026-10-26", "--refresh") in commands
    assert ("--trigger", "scheduled") in commands


@pytest.mark.parametrize("arguments", sorted(documented_commands()), ids=lambda a: " ".join(a) or "(no arguments)")
def test_every_documented_command_is_accepted_by_the_program(arguments, tmp_path, monkeypatch):
    """Parsed by the real argument parser, with the flow replaced by a stub: no Prefect, no ETL, only the command line."""
    for name in ("DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL", "PIPELINE_ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)  # a fresh checkout, whatever this machine has configured
    monkeypatch.setenv("PIPELINE_ENV_FILE", str(tmp_path / "no.env"))
    monkeypatch.setenv("PIPELINE_LOCAL_DB", str(tmp_path / "no-app.sqlite"))
    monkeypatch.setenv("PIPELINE_DEMO_DB", str(tmp_path / "demo.sqlite"))
    calls = []

    def stub(**kwargs):
        calls.append(kwargs)
        return pipeline.RunSummary("run-1", "Completed", kwargs["week_start"] or pipeline.wp.week_start_of(pipeline.date.today()))

    monkeypatch.setattr(pipeline, "weekly_office_performance_flow", stub)
    assert pipeline.main(list(arguments)) == 0
    assert len(calls) == 1
    if "--refresh" in arguments:
        assert calls[0]["refresh"] is True
    if "--trigger" in arguments:
        assert calls[0]["trigger"] == arguments[arguments.index("--trigger") + 1]


def test_the_options_the_design_document_lists_are_exactly_the_options_of_the_program(capsys):
    design = (REPO / "data" / "pipelines" / "PIPELINE_DESIGN.md").read_text(encoding="utf-8")
    synopsis = re.search(r"Opciones: `([^`]+)`", design).group(1)
    with pytest.raises(SystemExit):
        pipeline.main(["--help"])
    in_help = set(re.findall(r"--[a-z-]+", capsys.readouterr().out)) - {"--help"}
    assert set(re.findall(r"--[a-z-]+", synopsis)) == in_help
