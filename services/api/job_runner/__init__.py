"""Control of the background jobs: the ``job_runs`` table and the state machine that moves it. See ``models.py`` and ``service.py``.

A job lives outside the API (``scripts/nightly_export.py``), so nothing in this package imports FastAPI.
"""
