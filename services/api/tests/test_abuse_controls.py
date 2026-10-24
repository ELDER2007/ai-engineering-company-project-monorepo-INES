"""Abuse controls: the sliding-window limiter, the login lockout and the revocation of tokens on a password change."""

from __future__ import annotations

import time

import pytest
from httpx import ASGITransport, AsyncClient

from auth.security import create_access_token
from conftest import ALICE, BOB, FAR_FUTURE, PASSWORD, bearer, signed_token, uuid_of
from core.ratelimit import SlidingWindowLimiter
from main import app

pytestmark = pytest.mark.anyio

NEW_PASSWORD = "a-brand-new-password"


async def login(client, email: str, password: str):
    return await client.post("/auth/login", data={"username": email, "password": password})


# --- the limiter itself ---------------------------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_limiter_blocks_at_the_limit_and_frees_the_key_when_the_window_passes():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=3, window_seconds=60, clock=clock)

    for _ in range(3):
        assert limiter.retry_after("k") == 0
        limiter.record("k")
    assert 0 < limiter.retry_after("k") <= 61
    assert limiter.retry_after("another") == 0  # keys are independent

    clock.now += 61
    assert limiter.retry_after("k") == 0


def test_the_limiter_forgets_quiet_keys_and_can_be_cleared():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(limit=1, window_seconds=10, clock=clock)
    limiter.record("quiet")
    limiter.record("cleared")
    limiter.clear("cleared")
    clock.now += 11

    assert limiter.retry_after("quiet") == 0 and limiter.retry_after("cleared") == 0
    assert limiter._events == {}


# --- login lockout --------------------------------------------------------------------------------------


async def test_five_failed_logins_lock_that_client_and_email_even_for_the_right_password(async_client):
    for _ in range(5):
        assert (await login(async_client, ALICE, "wrong-password")).status_code == 401

    locked = await login(async_client, ALICE, PASSWORD)

    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0
    assert "access_token" not in locked.json()


async def test_a_successful_login_clears_the_failures_of_that_client_and_email(async_client):
    for _ in range(4):
        await login(async_client, ALICE, "wrong-password")
    assert (await login(async_client, ALICE, PASSWORD)).status_code == 200

    for _ in range(4):
        assert (await login(async_client, ALICE, "wrong-password")).status_code == 401  # counting from zero again


async def test_failing_for_one_email_does_not_lock_the_other_accounts_nor_other_clients(async_client):
    for _ in range(5):
        await login(async_client, ALICE, "wrong-password")

    assert (await login(async_client, BOB, PASSWORD)).status_code == 200  # same client, another email
    elsewhere = AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 4000)), base_url="http://testserver")
    async with elsewhere:
        assert (await login(elsewhere, ALICE, PASSWORD)).status_code == 200  # a victim is not locked out by an attacker


async def test_twenty_failures_from_one_client_lock_it_whatever_the_emails(async_client):
    for number in range(20):
        assert (await login(async_client, f"nobody{number}@example.com", "x")).status_code == 401

    assert (await login(async_client, BOB, PASSWORD)).status_code == 429


# --- tokens and password changes ------------------------------------------------------------------------


def old_token(email: str) -> str:
    """A token issued an hour ago, as if the user had logged in then."""
    return signed_token({"user_id": str(uuid_of(email)), "exp": FAR_FUTURE, "iat": int(time.time()) - 3600})


async def change_password(client, email: str):
    return await client.put(
        f"/users/{uuid_of(email)}",
        json={"password": NEW_PASSWORD, "current_password": PASSWORD},
        headers=bearer(create_access_token(uuid_of(email))),
    )


async def test_changing_the_password_cuts_off_the_tokens_issued_before_it(async_client):
    before = old_token(BOB)
    assert (await async_client.get("/auth/me", headers=bearer(before))).status_code == 200  # control

    assert (await change_password(async_client, BOB)).status_code == 200

    assert (await async_client.get("/auth/me", headers=bearer(before))).status_code == 401


async def test_a_token_issued_after_the_password_change_works(async_client):
    await change_password(async_client, BOB)

    token = (await login(async_client, BOB, NEW_PASSWORD)).json()["access_token"]

    assert (await async_client.get("/auth/me", headers=bearer(token))).status_code == 200


async def test_a_token_without_iat_is_cut_off_once_the_password_has_changed(async_client):
    legacy = signed_token({"user_id": str(uuid_of(BOB)), "exp": FAR_FUTURE})
    assert (await async_client.get("/auth/me", headers=bearer(legacy))).status_code == 200  # no change yet: accepted

    await change_password(async_client, BOB)

    assert (await async_client.get("/auth/me", headers=bearer(legacy))).status_code == 401


async def test_the_password_change_only_cuts_off_that_account(async_client):
    await change_password(async_client, BOB)

    assert (await async_client.get("/auth/me", headers=bearer(old_token(ALICE)))).status_code == 200
