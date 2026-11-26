"""Routes for the auth domain: login, the current session's user (with its
profile) and the password flows.

``POST /login`` follows the OAuth2 password flow: the form's ``username`` field
carries the email. User management lives in the ``users`` domain.

``POST /forgot-password`` and ``POST /reset-password`` are public by nature
(whoever forgot the password has no session); ``POST /change-password`` needs
one. Emails go out in a background task, after the response.

Mounted once in ``main.py``, at ``/auth``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from core import mailer
from core.config import get_access_token_expire_minutes
from core.ratelimit import SlidingWindowLimiter, client_host
from profiles import service as profiles_service
from profiles.schemas import ProfileMe
from users import service as users_service

from . import service
from .dependencies import CurrentUser
from .schemas import ChangePasswordIn, ForgotPasswordIn, MeOut, Message, ResetPasswordIn, Token
from .security import create_access_token

FORGOT_PASSWORD_MESSAGE = "If an account exists for that email, a reset link has been sent."

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
    return MeOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        role=user.role,
        created_at=user.created_at,
        profile=ProfileMe.from_profile(profile),
    )


def _send_password_reset(email: str) -> None:
    mail = service.request_password_reset(email)
    if mail is not None:
        mailer.deliver(mail)


@router.post("/forgot-password", response_model=Message)
async def forgot_password(payload: ForgotPasswordIn, background: BackgroundTasks) -> Message:
    """Public. Emails a single-use reset link if the account exists and is active.
    The answer is the same whether it does or not."""
    # Everything that depends on the account existing (lookup, token, email) runs after the
    # response, so neither its content nor its timing says whether the email is registered.
    background.add_task(_send_password_reset, payload.email)
    return Message(message=FORGOT_PASSWORD_MESSAGE)


@router.post("/reset-password", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(payload: ResetPasswordIn, background: BackgroundTasks) -> None:
    """Public. Sets a new password with the token from the emailed link (``400`` if
    it is unknown, already used or expired). It does not log the user in."""
    try:
        notice = service.reset_password(payload.token, payload.new_password)
    except service.InvalidResetTokenError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    background.add_task(mailer.deliver, notice)


@router.post("/change-password", response_model=None, status_code=status.HTTP_204_NO_CONTENT)
async def change_password(payload: ChangePasswordIn, user: CurrentUser, background: BackgroundTasks) -> None:
    """Changes the session's own password. ``400`` if ``current_password`` is wrong,
    ``422`` if the new one is the same or breaks the password rules."""
    try:
        notice = service.change_password(user, payload.current_password, payload.new_password)
    except users_service.WrongPasswordError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except service.SamePasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    background.add_task(mailer.deliver, notice)
