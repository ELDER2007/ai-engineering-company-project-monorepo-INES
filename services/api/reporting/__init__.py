"""Reporting domain: serves the results of the data pipelines (``data/pipelines/``).

Dependency direction: this package imports from ``data/pipelines``; the pipelines never
import from here. It is deliberately separate from telemetry: it does not touch
``GET /telemetry/report`` or ``services/telemetry/analysis.py``.
"""
