"""Routes for the talent applications.

``POST`` is public on purpose: it is how a visitor of the website applies, with no
account. ``GET`` exposes every candidate's personal data, so it is admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from auth.dependencies import admin_only
from core.ratelimit import SlidingWindowLimiter, client_host

from . import service
from .schemas import TalentApplicationCreate, TalentApplicationOut, TalentApplicationReceipt

router = APIRouter(tags=["talent"])

# The form is public, so each client address may submit a few applications per hour (a candidate
# normally sends one; retries after a validation error still fit). Every attempt counts, valid or not.
application_attempts = SlidingWindowLimiter(limit=10, window_seconds=60 * 60)


def limit_submissions(request: Request) -> None:
    host = client_host(request)
    wait = application_attempts.retry_after(host)
    if wait:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many applications from this address. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    application_attempts.record(host)


@router.post(
    "", response_model=TalentApplicationReceipt, status_code=status.HTTP_201_CREATED, dependencies=[Depends(limit_submissions)]
)
async def create_application(payload: TalentApplicationCreate) -> TalentApplicationReceipt:
    return service.create_application(payload)


@router.get("", response_model=list[TalentApplicationOut], dependencies=[Depends(admin_only)])
async def list_applications() -> list[TalentApplicationOut]:
    return service.list_applications()
