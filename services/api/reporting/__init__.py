"""Reporting domain: HTTP access to the results of the data pipelines (``data/pipelines/``).

This package only handles HTTP (session, role, parameters, status codes). It holds no SQL and no ETL logic: every
endpoint calls one function of ``data/pipelines/weekly_office_performance/interface.py``. The dependency goes one way:
this package imports from ``data/pipelines``; the pipelines never import from here. It is separate from telemetry: it
does not touch ``GET /telemetry/report`` or ``telemetry/analysis.py``.
"""

import sys
from pathlib import Path

# This package imports ``data`` (``data/pipelines/``), which lives at the ROOT of the repository, outside ``services/api``. Under pytest the
# root is on the path (``pyproject.toml``: ``pythonpath = [".", "../.."]``). For a person who runs ``uvicorn main:app`` from ``services/api`` it
# is not, and the API would not even start (``ModuleNotFoundError: No module named 'data'``). So it is added here, before anything imports
# ``data``: every module of this package is imported after this file. It goes at the END of the path (``append``): the root holds folders
# (``data``, ``src``, ``scripts``...) that must never win over the API's own modules.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
