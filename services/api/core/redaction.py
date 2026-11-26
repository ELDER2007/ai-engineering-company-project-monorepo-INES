"""Credentials never reach a log, a column or an answer: the message of a database error can carry the URL it was connecting to.

Shared by the background jobs (``job_runner``) and the asynchronous tasks (``async_tasks``). It lives here, and not in either of them, because it must
not import any table: importing a module that declares tables registers them in SQLModel's shared metadata, and the inventory would then create them
in its own database at startup.
"""

from __future__ import annotations

import re

MAX_ERROR_LENGTH = 2000
# scheme://user:password@host -> scheme://***@host. The look-behind makes a scheme start where its run of letters starts: without it the engine tried every
# letter of a long run as a start (cost quadratic in the length: 40 000 letters took 10 s, and the message of an error can be that long).
_CREDENTIALS = re.compile(r"(?<![a-z0-9+.-])([a-z][a-z0-9+.-]*://)[^\s/@]*@", re.IGNORECASE)


def strip_credentials(text: str) -> str:
    """``text`` without the user and password of any connection URL (``scheme://user:password@host`` -> ``scheme://***@host``)."""
    return _CREDENTIALS.sub(r"\1***@", str(text))


def redact(text: str) -> str:
    """``strip_credentials`` and cut to a size a column can hold. The message of a database error can carry the URL it was
    connecting to: it must never reach ``error_message`` or a log."""
    return strip_credentials(text)[:MAX_ERROR_LENGTH]
