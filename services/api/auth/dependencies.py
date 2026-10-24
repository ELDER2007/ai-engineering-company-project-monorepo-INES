"""FastAPI dependency that enforces authentication.

``get_current_user`` is attached at router level to every protected domain, so
a new route there is private by default. A valid session for an active user is
all it takes (401 = no valid session); ``role`` is stored but no route checks it yet.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from users import service as users_service
from users.schemas import Role, UserOut

from .security import decode_access_claims

# tokenUrl only feeds the "Authorize" button in /docs (its "username" box takes the email).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserOut:
    decoded = decode_access_claims(token)
    if decoded is None:
        raise _UNAUTHORIZED
    user_id, issued_at = decoded
    doc = users_service.get_doc(user_id)
    if doc is None or not doc["is_active"]:  # deleted or deactivated after the token was issued
        raise _UNAUTHORIZED
    if _issued_before_password_change(doc, issued_at):
        raise _UNAUTHORIZED
    return UserOut.model_validate(doc)


def _issued_before_password_change(doc: dict, issued_at: int | None) -> bool:
    """True when the password changed after the token was issued. ``iat`` has one-second resolution, so a
    token issued in the very second of the change is not cut off. A token without ``iat`` (from before
    this check existed) is cut off as soon as the account has ever changed its password."""
    changed = doc.get("password_changed_at")
    if not changed:
        return False
    return issued_at is None or issued_at < int(datetime.fromisoformat(changed).timestamp())


CurrentUser = Annotated[UserOut, Depends(get_current_user)]


def owner_or_admin(user_id: UUID, current: CurrentUser) -> None:
    """Dependency for routes shaped ``/{user_id}``: that user or any admin may pass
    (``403`` for anyone else, before the target is even looked up)."""
    if current.id != user_id and current.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only access your own account")


def owner_only(user_id: UUID, current: CurrentUser) -> None:
    """Dependency for routes shaped ``/{user_id}`` that only the owner may use, not even an admin."""
    if current.id != user_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only change your own profile")


def admin_only(current: CurrentUser) -> None:
    """Dependency for routes that expose everybody's data at once."""
    if current.role != Role.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Admins only")
