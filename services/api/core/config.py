"""Cross-cutting app configuration. No business logic lives here."""

from __future__ import annotations

import os


def get_allowed_origins() -> list[str]:
    """CORS origins, from the ALLOWED_ORIGINS env var (comma-separated).

    Falls back to the local Vite dev servers for uis/website and
    uis/backoffice so the API is usable out of the box in development.
    Production deployments must set ALLOWED_ORIGINS explicitly.
    """
    raw = os.environ.get("ALLOWED_ORIGINS")
    if raw:
        return [origin.strip() for origin in raw.split(",") if origin.strip()]
    return [
        "http://localhost:5173",
        "http://localhost:5174",
    ]
