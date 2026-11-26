"""Logging for the whole app, set up once at start-up.

Without this the loggers of the app have no handler: ``INFO`` lines (migrations, the first user)
are never shown and the others have no date or level. ``LOG_LEVEL`` (default ``INFO``) changes it.

The access log of uvicorn writes the whole URL of every request. For the incident list that
means the text typed in the search box and the client filter, so only the path is kept.
"""

from __future__ import annotations

import logging
import os


class _DropQueryString(logging.Filter):
    """Keep the path of an access-log line and drop what follows the ``?``."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def configure_logging() -> None:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if not isinstance(logging.getLevelName(level), int):  # an unknown name comes back as "Level X"
        level = "INFO"
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    else:
        root.setLevel(level)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _DropQueryString) for f in access.filters):
        access.addFilter(_DropQueryString())
