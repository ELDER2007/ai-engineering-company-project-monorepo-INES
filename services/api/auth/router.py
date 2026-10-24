"""Routes for the auth domain: login and the current session's user (with its profile).

``POST /login`` follows the OAuth2 password flow: the form's ``username`` field
carries the email. User management lives in the ``users`` domain.

Mounted once in ``main.py``, at ``/auth``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from core.config import get_access_token_expire_minutes
from core.ratelimit import SlidingWindowLimiter, client_host
from profiles import service as profiles_service

from . import service
from .dependencies import CurrentUser
from .schemas import MeOut, Token
from .security import create_access_token

router = APIRouter(tags=["auth"])

# Abuse control for POST /login. Only *failed* attempts count, so normal use never hits it.
# The pair (client, email) is limited, not the email alone: otherwise anybody could lock a victim
# out just by failing logins for their address. A per-client cap covers guessing across many emails.
LOGIN_WINDOW_SECONDS = 15 * 60
pair_failures = SlidingWindowLimiter(limit=5, window_seconds=LOGIN_WINDOW_SECONDS)
client_failures = SlidingWindowLimiter(limit=20, window_seconds=LOGIN_WINDOW_SECONDS)


@router.post("/login", response_model=Token)
async def login(request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    host = client_host(request)
    pair = f"{host}|{form.username.strip().casefold()}"
    wait = max(pair_failures.retry_after(pair), client_failures.retry_after(host))
    if wait:  # refused before checking the password: a locked client cannot even confirm a correct one
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    user = service.authenticate(form.username, form.password)  # username = email
    if user is None:
        pair_failures.record(pair)
        client_failures.record(host)
        # Same answer for an unknown email and a wrong password.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    pair_failures.clear(pair)
    return Token(
        access_token=create_access_token(user.id),
        expires_in=get_access_token_expire_minutes() * 60,
    )


@router.get("/me", response_model=MeOut)
async def read_me(user: CurrentUser) -> MeOut:
    profile = profiles_service.ensure_profile(user.id, user.email)  # self-heals a missing profile
    return MeOut(**user.model_dump(), profile=profile)
