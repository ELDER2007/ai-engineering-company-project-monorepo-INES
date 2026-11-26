"""Business logic for the auth domain: checking credentials at login, and the
password flows (forgotten-password reset by email, and change while logged in).

Pending reset tokens live in their own TinyDB file (``auth/db.json``), one
document per token: ``{token_hash, user_id, password_fingerprint, created_at,
expires_at}``. The token is a signed JWT (see
``security.new_reset_token``); only its SHA-256 is stored. A token is single-use,
expires (``PASSWORD_RESET_EXPIRE_MINUTES``) and is replaced by a newer one. It
is also tied to the password it was issued for (``password_fingerprint``), so
it dies as soon as that password changes, by whatever route.

The functions here do not send anything: they return the ``Mail`` to send (or
``None``), and the router hands it to a background task.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

from tinydb import Query, TinyDB

from core.config import get_frontend_url, get_password_reset_expire_minutes, get_password_resets_db_path
from core.mailer import Mail
from profiles import service as profiles_service
from users import service as users_service
from users.schemas import UserOut

from . import emails
from .security import hash_password, hash_reset_token, new_reset_token, verify_password, verify_reset_token

# Verified against when the email doesn't exist, so a login attempt takes
# about the same time either way and can't be used to enumerate accounts.
_DUMMY_HASH = hash_password("not-a-real-password")

# One reset email per account in this window: the public endpoint can't be used
# to flood somebody's inbox.
RESET_COOLDOWN_SECONDS = 60

_db: TinyDB | None = None


class InvalidResetTokenError(Exception):
    def __init__(self):
        """One answer for unknown, used, expired and orphaned tokens alike."""
        super().__init__("Invalid or expired reset link")


class SamePasswordError(Exception):
    def __init__(self):
        super().__init__("The new password must be different from the current one")


def get_db() -> TinyDB:
    global _db
    if _db is None:
        _db = TinyDB(get_password_resets_db_path())
    return _db


def authenticate(email: str, password: str) -> UserOut | None:
    """The user if the credentials are valid and the account is active."""
    doc = users_service.get_doc_by_email(email)
    password_ok = verify_password(password, doc["hashed_password"] if doc else _DUMMY_HASH)
    # An inactive account gets the same answer as a wrong password.
    if doc is None or not password_ok or not doc["is_active"]:
        return None
    return UserOut.model_validate(doc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _name_of(user_id: UUID | str, email: str) -> str:
    return profiles_service.ensure_profile(user_id, email).name


def _fingerprint(hashed_password: str) -> str:
    """Identifies a stored password without copying its bcrypt hash into another file."""
    return hashlib.sha256(hashed_password.encode("utf-8")).hexdigest()


def _discard_tokens(user_id: UUID | str) -> None:
    get_db().remove(Query().user_id == str(user_id))


def request_password_reset(email: str) -> Mail | None:
    """Issue a reset token for the account with that email and return the email
    carrying the link. ``None`` (nothing to send) for an unknown email, a
    deactivated account, or one that was sent a link less than a minute ago:
    the caller answers the same in every case."""
    now = _now()
    get_db().remove(Query().expires_at.test(lambda value: datetime.fromisoformat(value) <= now))  # housekeeping

    doc = users_service.get_doc_by_email(email)
    if doc is None or not doc["is_active"]:
        return None
    pending = get_db().search(Query().user_id == doc["id"])
    if any(now - datetime.fromisoformat(p["created_at"]) < timedelta(seconds=RESET_COOLDOWN_SECONDS) for p in pending):
        return None

    minutes = get_password_reset_expire_minutes()
    token, token_hash = new_reset_token(doc["id"])
    _discard_tokens(doc["id"])  # only the newest link works
    get_db().insert(
        {
            "token_hash": token_hash,
            "user_id": doc["id"],
            "password_fingerprint": _fingerprint(doc["hashed_password"]),
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=minutes)).isoformat(),
        }
    )
    link = f"{get_frontend_url()}/reset-password?{urlencode({'token': token})}"
    return emails.password_reset(doc["email"], _name_of(doc["id"], doc["email"]), link, minutes)


def reset_password(token: str, new_password: str) -> Mail:
    """Set a new password with an emailed token, and return the "your password
    changed" notice for the owner. The token is spent, together with any other
    pending one of that user."""
    owner = verify_reset_token(token)  # signature, purpose and expiry, before touching the store
    pending = get_db().get(Query().token_hash == hash_reset_token(token)) if owner else None
    if pending is None or pending["user_id"] != str(owner) or datetime.fromisoformat(pending["expires_at"]) <= _now():
        raise InvalidResetTokenError()
    doc = users_service.get_doc(UUID(pending["user_id"]))
    # Deleted or deactivated after the email went out, or the password was changed in the meantime.
    if (
        doc is None
        or not doc["is_active"]
        or pending["password_fingerprint"] != _fingerprint(doc["hashed_password"])
    ):
        _discard_tokens(pending["user_id"])
        raise InvalidResetTokenError()
    users_service.set_password(UUID(doc["id"]), new_password)
    _discard_tokens(doc["id"])
    return emails.password_changed(doc["email"], _name_of(doc["id"], doc["email"]))


def change_password(user: UserOut, current_password: str, new_password: str) -> Mail:
    """Change the session's own password, proving the current one. Returns the
    notice for the owner. Raises ``users.service.WrongPasswordError`` or
    ``SamePasswordError``."""
    doc = users_service.get_doc(user.id)
    if doc is None:
        raise users_service.UserNotFoundError(user.id)
    if not verify_password(current_password, doc["hashed_password"]):
        raise users_service.WrongPasswordError()
    if verify_password(new_password, doc["hashed_password"]):
        raise SamePasswordError()
    users_service.set_password(user.id, new_password)
    _discard_tokens(user.id)  # a reset link requested earlier must not undo this change
    return emails.password_changed(doc["email"], _name_of(doc["id"], doc["email"]))
