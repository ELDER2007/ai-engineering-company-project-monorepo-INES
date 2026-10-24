"""Routes for the talent applications.

``POST`` is public on purpose: it is how a visitor of the website applies, with no
account. ``GET`` exposes every candidate's personal data, so it is admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from auth.dependencies import admin_only

from . import service
from .schemas import TalentApplicationCreate, TalentApplicationOut, TalentApplicationReceipt

router = APIRouter(tags=["talent"])


@router.post("", response_model=TalentApplicationReceipt, status_code=status.HTTP_201_CREATED)
async def create_application(payload: TalentApplicationCreate) -> TalentApplicationReceipt:
    return service.create_application(payload)


@router.get("", response_model=list[TalentApplicationOut], dependencies=[Depends(admin_only)])
async def list_applications() -> list[TalentApplicationOut]:
    return service.list_applications()
