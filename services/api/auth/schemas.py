"""Pydantic contracts for the auth domain. Users live in ``users``."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from profiles.schemas import Profile
from users.schemas import Email, NewPassword, UserOut


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until the token expires (ACCESS_TOKEN_EXPIRE_MINUTES * 60)


class MeOut(UserOut):
    """``GET /auth/me``: the session's user (``email``, ``role``, ...) and its linked
    Profile (``name`` and the contact data). Never the password or its hash."""

    profile: Profile


class ForgotPasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Email


class ResetPasswordIn(BaseModel):
    """``token`` is the one from the emailed link; ``new_password`` follows the sign-up rules."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=1000)
    new_password: NewPassword


class ChangePasswordIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1)
    new_password: NewPassword


class Message(BaseModel):
    message: str
