"""Storage for the talent applications, in TinyDB like the other small domains.

Single-process by design (see the API README limitations). Duplicate emails are
accepted: a candidate may apply again with updated data and the team sees every submission.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from tinydb import TinyDB

from core.config import get_talent_db_path

from .schemas import TalentApplicationCreate, TalentApplicationOut, TalentApplicationReceipt

_db: TinyDB | None = None


def get_db() -> TinyDB:
    global _db
    if _db is None:
        path = get_talent_db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _db = TinyDB(path)
    return _db


def create_application(payload: TalentApplicationCreate) -> TalentApplicationReceipt:
    application = TalentApplicationOut(
        id=uuid4(), created_at=datetime.now(timezone.utc), **payload.model_dump()
    )
    get_db().insert(application.model_dump(mode="json"))
    return TalentApplicationReceipt(id=application.id, created_at=application.created_at)


def list_applications() -> list[TalentApplicationOut]:
    docs = sorted(get_db().all(), key=lambda doc: doc["created_at"], reverse=True)
    return [TalentApplicationOut.model_validate(doc) for doc in docs]
