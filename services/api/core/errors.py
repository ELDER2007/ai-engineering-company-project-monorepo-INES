"""Error handling shared by the whole app.

Every error the API sends is JSON with a ``detail`` field:

* a validation error (422): ``detail`` is a list of ``{type, loc, msg}``. The rejected ``input`` and
  its ``ctx`` are never echoed: they can be a password, the customer's email or a phone number,
  and a ``NaN`` among them cannot even be serialised.
* a domain error (4xx): ``detail`` is a sentence.
* the data files cannot be read or written: ``503`` with a generic sentence.
* anything unexpected: ``500`` with a generic sentence and an ``error_id``. The same id is written
  to the server log with the call stack, so a report can be matched with its cause. The text of
  the exception is left out of the log on purpose: a validation error quotes the rejected value.
"""

from __future__ import annotations

import logging
import traceback
import uuid

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Internal server error. Please try again later."
UNAVAILABLE_MESSAGE = "The service is temporarily unavailable. Please try again later."


class DatabaseUnavailableError(Exception):
    """A data file cannot be read or written (damaged JSON, missing permissions...)."""


async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = [{k: v for k, v in error.items() if k not in ("input", "ctx")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


async def database_unavailable_handler(request: Request, exc: DatabaseUnavailableError):
    logger.error("Data store unavailable on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": UNAVAILABLE_MESSAGE})


async def catch_unhandled_errors(request: Request, call_next):
    """Turn any exception no route handled into a generic JSON ``500``.

    It sits inside the CORS middleware (see ``main.py``), so the browser can read the answer
    instead of seeing an opaque network error.
    """
    try:
        return await call_next(request)
    except Exception as exc:  # noqa: BLE001 - this is the last line of defence
        error_id = uuid.uuid4().hex[:8]
        logger.error(
            "Unhandled %s [%s] on %s %s\n%s",
            type(exc).__name__,
            error_id,
            request.method,
            request.url.path,
            "".join(traceback.format_tb(exc.__traceback__)),
        )
        return JSONResponse(status_code=500, content={"detail": INTERNAL_ERROR_MESSAGE, "error_id": error_id})
