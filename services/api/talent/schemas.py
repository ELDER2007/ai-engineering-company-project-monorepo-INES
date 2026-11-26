"""Pydantic contracts for the talent applications (website "Únete a Nexova" form).

The rules mirror ``uis/website/src/TalentForm.tsx`` so the API refuses with a ``422``
whatever the browser would have refused, and does not trust the browser to have checked.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)

PHONE_PATTERN = re.compile(r"^\+\d{1,3}\s[\d\s]{6,14}$")
COMMENTS_MAX = 500
LINKEDIN_MAX = 300


class Country(StrEnum):
    SPAIN = "spain"
    USA = "usa"
    OTHER = "other"


class Sector(StrEnum):
    TECHNOLOGY = "technology"
    RETAIL = "retail"
    FINANCIAL_SERVICES = "financial_services"
    CONSULTING = "consulting"
    OTHER = "other"


class EnglishLevel(StrEnum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    NATIVE = "native"


class Availability(StrEnum):
    IMMEDIATE = "immediate"
    ONE_MONTH = "one_month"
    TWO_THREE_MONTHS = "two_three_months"
    EXPLORING = "exploring"


def _normalize_email(value):
    return value.strip().casefold() if isinstance(value, str) else value


def _blank_to_none(value):
    if isinstance(value, str):
        value = value.strip()
    return value or None


class TalentApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=120)]
    email: Annotated[EmailStr, BeforeValidator(_normalize_email)]
    phone: Annotated[str, StringConstraints(strip_whitespace=True)]
    country: Country
    experience_years: int = Field(ge=0, le=50)
    sector: Sector
    english_level: EnglishLevel
    availability: Availability
    linkedin_url: Annotated[str | None, BeforeValidator(_blank_to_none)] = None
    comments: Annotated[str, StringConstraints(max_length=COMMENTS_MAX)] = ""
    consent: Literal[True]  # the data-processing policy must be accepted; false or missing is a 422

    @field_validator("full_name")
    @classmethod
    def _name_and_surname(cls, value: str) -> str:
        if len(value.split()) < 2:
            raise ValueError("full_name must contain at least a name and a surname")
        return value

    @field_validator("phone")
    @classmethod
    def _phone_with_country_code(cls, value: str) -> str:
        if not PHONE_PATTERN.match(value):
            raise ValueError("phone must include the country code, e.g. +34 612 345 678")
        return value

    @field_validator("linkedin_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is not None and not (re.match(r"^https?://\S+$", value) and len(value) <= LINKEDIN_MAX):
            raise ValueError(f"linkedin_url must be an http(s) URL of at most {LINKEDIN_MAX} characters")
        return value


class TalentApplicationReceipt(BaseModel):
    """What the public endpoint answers: no personal data is echoed back."""

    id: UUID
    created_at: datetime


class TalentApplicationOut(TalentApplicationCreate):
    id: UUID
    created_at: datetime
