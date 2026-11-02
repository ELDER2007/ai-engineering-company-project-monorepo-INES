"""Pydantic contracts for the profiles domain.

A Profile holds the person's name and contact data. None of it lives in
``User`` (which is only credentials and account state). Profile and User are
one-to-one: ``Profile.user_id`` is the ``User.id`` it belongs to.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from users.schemas import Email

from .fields import ADDRESS_MAX, NAME_MAX, PHONE_PATTERN


class Profile(BaseModel):
    """The document stored in TinyDB (``profiles/db.json``). Never returned as is: the API
    answers with ``ProfileMe`` or ``ProfileOut``, which leave the internal ``id`` out.
    ``name`` is required; the rest is optional."""

    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: str
    contact_email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None


class ProfileMe(BaseModel):
    """Your own profile (``/auth/me``, ``/profiles/me``): the editable data and nothing else.
    No ``id`` (storage key) and no ``user_id`` (it is the session's own id)."""

    name: str
    contact_email: EmailStr | None
    phone: str | None
    address: str | None

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileMe:
        return cls(
            name=profile.name,
            contact_email=profile.contact_email,
            phone=profile.phone,
            address=profile.address,
        )


class ProfileOut(BaseModel):
    """A profile addressed by user (``/profiles`` for admins, ``/profiles/{user_id}``):
    ``user_id`` says whose it is. The profile's own storage ``id`` never leaves the API."""

    user_id: UUID
    name: str
    contact_email: EmailStr | None
    phone: str | None
    address: str | None

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileOut:
        return cls(
            user_id=profile.user_id,
            name=profile.name,
            contact_email=profile.contact_email,
            phone=profile.phone,
            address=profile.address,
        )


class ProfileUpdate(BaseModel):
    """``PUT /profiles/me``: partial update of your own profile. Omitted fields are
    left untouched; an explicit ``null`` clears an optional field (but not the name)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=NAME_MAX)
    contact_email: Email | None = None
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    address: str | None = Field(default=None, min_length=1, max_length=ADDRESS_MAX)

    @field_validator("name")
    @classmethod
    def name_not_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("name cannot be cleared")
        return value
