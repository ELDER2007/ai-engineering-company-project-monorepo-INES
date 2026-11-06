"""Reporting domain: HTTP access to the results of the data pipelines (``data/pipelines/``).

This package only handles HTTP (session, role, parameters, status codes). It holds no SQL and no ETL logic: every
endpoint calls one function of ``data/pipelines/weekly_office_performance/interface.py``. The dependency goes one way:
this package imports from ``data/pipelines``; the pipelines never import from here. It is separate from telemetry: it
does not touch ``GET /telemetry/report`` or ``telemetry/analysis.py``.
"""
