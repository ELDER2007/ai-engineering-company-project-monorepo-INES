"""The API starts the way its README says: ``uvicorn main:app`` from ``services/api``, with nothing else set.

The reporting module imports the ``data`` package (``data/pipelines/``), which lives at the root of the repository, outside ``services/api``.
Under pytest that works because ``pyproject.toml`` puts the root on the path (``pythonpath = [".", "../.."]``): a test that imports ``main`` in
this process would pass even if the API could not start for a person who runs it. So these tests start a NEW process, from ``services/api``,
without ``PYTHONPATH`` and without pytest, exactly as a reviewer would.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]
REPO = API.parents[1]


def run_python(code: str, tmp_path: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}  # no help from the environment
    env.update(
        DATABASE_URL=f"sqlite:///{tmp_path / 'never-used.sqlite'}",  # importing the API opens no connection, but nothing real can be reached either
        TELEMETRY_DATABASE_URL="",
        REPORTING_DATABASE_URL="",
        PIPELINE_ENV_FILE="/nonexistent/.env",
    )
    return subprocess.run([sys.executable, "-c", code], cwd=API, env=env, capture_output=True, text=True, timeout=120, check=False)


def test_the_api_imports_from_its_own_folder_with_no_pythonpath_and_no_pytest(tmp_path):
    out = run_python("import main; print('STARTED', main.app.title)", tmp_path)
    assert out.returncode == 0, out.stderr[-600:]
    assert "STARTED" in out.stdout


def test_the_reporting_routes_are_there_once_it_has_started(tmp_path):
    out = run_python("import main; print(sorted(p for p in main.app.openapi()['paths'] if p.startswith('/reporting')))", tmp_path)  # what Swagger shows
    assert out.returncode == 0, out.stderr[-600:]
    assert "/reporting/pipeline-runs" in out.stdout and "/reporting/weekly-office-program-performance" in out.stdout


def test_the_repo_root_is_added_at_the_end_of_the_path_so_it_can_never_shadow_a_module_of_the_api(tmp_path):
    """``append``, not ``insert(0)``: the root holds folders (``data``, ``src``, ``scripts``...) that must never win over the API's own modules."""
    code = ("import sys, main;"
            f"root = {str(REPO)!r};"
            "paths = [p for p in sys.path if p];"
            "print('LAST' if root in sys.path and sys.path.index(root) > max(i for i, p in enumerate(sys.path) if p.endswith('services/api') or p == '')"
            " else 'NOT_LAST')")
    out = run_python(code, tmp_path)
    assert out.returncode == 0, out.stderr[-600:]
    assert out.stdout.strip() == "LAST"


def test_the_api_modules_are_still_the_ones_of_services_api(tmp_path):
    out = run_python("import main, core, auth, users, reporting; print(core.__file__.endswith('services/api/core/__init__.py'), reporting.__file__.endswith('services/api/reporting/__init__.py'))", tmp_path)
    assert out.returncode == 0, out.stderr[-600:]
    assert out.stdout.strip() == "True True"
