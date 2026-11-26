"""Password hashing and JWT helpers. Pure functions, no I/O (apart from the log).

Passwords are only ever stored as bcrypt hashes, through libpass (``libpass[bcrypt]``).
Why a token or a hash was refused is logged by kind only: never the token, never the password."""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from passlib.hash import bcrypt  # libpass (maintained passlib fork, same import), not the abandoned passlib

from core.config import (
    JWT_ALGORITHM,
    get_access_token_expire_minutes,
    get_jwt_secret,
    get_password_reset_expire_minutes,
)

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    """bcrypt hash (``$2b$...``, own salt). Every password operation goes through here."""
    return bcrypt.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.verify(password, hashed_password)
    except ValueError:  # malformed hash, or a password longer than bcrypt's 72-byte limit
        # Same answer as a wrong password, but a damaged hash must not look like a forgotten one.
        logger.warning("A stored password hash is malformed or the password exceeds bcrypt's limit")
        return False


def create_access_token(user_uuid: UUID | str) -> str:
    """Signed JWT (HS256, python-jose) with the minimum claims: ``user_id`` (the
    user's ``id`` stored in TinyDB), ``exp`` and ``iat`` (when it was issued: it is what lets a
    password change cut off the tokens issued before it). Who the user is and
    whether they still exist is read from the store on every request, so
    deleting an account takes effect immediately instead of when the token
    expires. The uuid never changes, so editing the email keeps the session.

    Lifetime: ``ACCESS_TOKEN_EXPIRE_MINUTES`` (see ``core.config``).
    """
    issued = datetime.now(timezone.utc)
    expires = issued + timedelta(minutes=get_access_token_expire_minutes())
    claims = {"user_id": str(user_uuid), "exp": expires, "iat": issued}
    return jwt.encode(claims, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> UUID | None:
    """The ``user_id`` in a valid, unexpired, correctly signed token, or ``None``
    for anything else (bad signature, expired, wrong algorithm, no ``exp`` or an
    ``exp`` that is not a number, ``user_id`` missing or not a uuid)."""
    decoded = decode_access_claims(token)
    return decoded[0] if decoded else None


def decode_access_claims(token: str) -> tuple[UUID, int | None] | None:
    """Like ``decode_access_token`` but also returns ``iat`` (epoch seconds), or ``None`` for a token
    that carries none (issued before ``iat`` existed)."""
    try:
        claims = jwt.decode(
            token,
            get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],  # pinned: never trust the header's alg
            options={"require_exp": True},
        )
        if "purpose" in claims:  # minted for something else (a password reset), never a session
            return None
        raw = claims["user_id"]
        if not isinstance(raw, str):
            return None
        issued_at = claims.get("iat")
        return UUID(raw), (int(issued_at) if issued_at is not None else None)
    except ExpiredSignatureError:
        logger.info("Rejected an expired token")  # the normal end of a session
        return None
    except (JWTError, KeyError, ValueError, TypeError) as exc:  # TypeError: python-jose on an ``exp`` of null or a list
        # A bad signature or a changed algorithm is not an expired session: it may be someone tampering.
        logger.warning("Rejected an invalid token (%s)", type(exc).__name__)
        return None


RESET_PURPOSE = "password_reset"


def new_reset_token(user_uuid: UUID | str) -> tuple[str, str]:
    """A signed password-reset token and its hash: ``(token, token_hash)``.

    A JWT (HS256, the same ``SECRET_KEY`` as the sessions) with ``user_id``, a
    ``purpose`` that keeps it from ever being accepted as a session token (and
    the other way round), a random ``jti`` and a short ``exp``
    (``PASSWORD_RESET_EXPIRE_MINUTES``). It only travels in the email; the store
    keeps its hash, which is what makes it single-use.
    """
    expires = datetime.now(timezone.utc) + timedelta(minutes=get_password_reset_expire_minutes())
    claims = {
        "user_id": str(user_uuid),
        "purpose": RESET_PURPOSE,
        "jti": secrets.token_urlsafe(16),
        "exp": expires,
    }
    token = jwt.encode(claims, get_jwt_secret(), algorithm=JWT_ALGORITHM)
    return token, hash_reset_token(token)


def verify_reset_token(token: str) -> UUID | None:
    """The ``user_id`` of a correctly signed, unexpired reset token, or ``None`` for
    anything else (forged, expired, or a token minted for another purpose)."""
    try:
        claims = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM], options={"require_exp": True})
        if claims.get("purpose") != RESET_PURPOSE or not isinstance(claims.get("user_id"), str):
            return None
        return UUID(claims["user_id"])
    except (JWTError, ValueError):
        return None


def hash_reset_token(token: str) -> str:
    """SHA-256: the token is already unguessable, and it has to be looked up by its hash."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
