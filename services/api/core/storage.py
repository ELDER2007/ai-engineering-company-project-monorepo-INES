"""Opening the TinyDB files, in one place, with one way of failing."""

from __future__ import annotations

from pathlib import Path

from tinydb import TinyDB

from .errors import DatabaseUnavailableError


def open_database(path: Path) -> TinyDB:
    """Open (or create) a TinyDB file.

    A damaged file or one that cannot be read or written raises ``DatabaseUnavailableError``
    (a ``503`` in the API) instead of a raw ``JSONDecodeError`` / ``PermissionError``. Only the
    file name and the kind of error are kept: the path is internal and the content may be personal.
    """
    database = None
    try:
        database = TinyDB(path)
        len(database)  # TinyDB reads the file lazily: reading it now is what finds a damaged one
        return database
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        if database is not None:
            database.close()
        raise DatabaseUnavailableError(f"{path.name}: {type(exc).__name__}") from exc
