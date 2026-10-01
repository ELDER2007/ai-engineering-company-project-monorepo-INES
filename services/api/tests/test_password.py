"""Password flows: forgotten-password reset by email and change while logged in."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from auth import service as auth_service
from auth.security import hash_reset_token
from conftest import ALICE, BOB, PASSWORD, headers_for, uuid_of
from core import mailer
from core.config import get_frontend_url, get_password_reset_expire_minutes
from main import app

NEW_PASSWORD = "brand-new-pass"


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("FRONTEND_URL", "https://backoffice.example.com/")
    return TestClient(app)


def login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def forgot(client, email=BOB):
    return client.post("/auth/forgot-password", json={"email": email})


def reset(client, token, new_password=NEW_PASSWORD):
    return client.post("/auth/reset-password", json={"token": token, "new_password": new_password})


def token_in(mail: mailer.Mail) -> str:
    """The token of the reset link, as the person reading the email would get it."""
    link = re.search(r"https?://\S+", mail.text).group()
    return parse_qs(urlparse(link).query)["token"][0]


def issue(client, outbox, email=BOB) -> str:
    assert forgot(client, email).status_code == 200
    return token_in(outbox[-1])


def skip_cooldown(resets_db):
    """Age the pending tokens as if they had been requested two minutes ago."""
    earlier = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
    resets_db.update({"created_at": earlier})


# --- forgot-password -------------------------------------------------------------


def test_forgot_password_emails_a_link_to_the_frontend(client, outbox, resets_db):
    response = forgot(client, "  BOB@Example.com ")
    assert response.status_code == 200
    [mail] = outbox
    assert mail.to == BOB and "contraseña" in mail.subject
    token = token_in(mail)
    assert f"https://backoffice.example.com/reset-password?token={token}" in mail.text
    assert token in mail.html and "Hola, bob:" in mail.text  # the profile name
    assert "30 minutos" in mail.text


def test_only_the_hash_of_the_token_is_stored(client, outbox, resets_db, users_db):
    token = issue(client, outbox)
    [stored] = resets_db.all()
    assert set(stored) == {"token_hash", "user_id", "password_fingerprint", "created_at", "expires_at"}
    assert stored["token_hash"] == hash_reset_token(token) and token not in json.dumps(stored)
    assert stored["user_id"] == str(uuid_of(BOB))
    hashed_password = next(d for d in users_db.all() if d["email"] == BOB)["hashed_password"]
    assert hashed_password not in json.dumps(stored)
    lifetime = datetime.fromisoformat(stored["expires_at"]) - datetime.fromisoformat(stored["created_at"])
    assert lifetime == timedelta(minutes=30)


def test_forgot_password_answers_the_same_for_unknown_and_inactive_accounts(client, outbox, resets_db, users_db):
    known = forgot(client, BOB)
    users_db.update({"is_active": False}, lambda d: d["email"] == ALICE)
    for email in ("nobody@example.com", ALICE):
        response = forgot(client, email)
        assert (response.status_code, response.json()) == (known.status_code, known.json())
    assert [mail.to for mail in outbox] == [BOB] and len(resets_db) == 1


def test_forgot_password_validates_the_body(client, outbox):
    for bad in ({}, {"email": "not-an-email"}, {"email": BOB, "extra": 1}):
        assert client.post("/auth/forgot-password", json=bad).status_code == 422, bad
    assert outbox == []


def test_a_second_request_within_the_cooldown_sends_nothing(client, outbox, resets_db):
    first = issue(client, outbox)
    assert forgot(client).status_code == 200  # same answer...
    assert len(outbox) == 1 and len(resets_db) == 1  # ...but no second email
    assert reset(client, first).status_code == 204  # and the first link still works


def test_a_newer_link_replaces_the_older_one(client, outbox, resets_db):
    first = issue(client, outbox)
    skip_cooldown(resets_db)
    second = issue(client, outbox)
    assert first != second and len(resets_db) == 1
    assert reset(client, first).status_code == 400
    assert reset(client, second).status_code == 204


def test_expired_tokens_are_swept_on_the_next_request(client, outbox, resets_db):
    issue(client, outbox, BOB)
    resets_db.update({"expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    forgot(client, "nobody@example.com")
    assert len(resets_db) == 0


def test_the_link_lifetime_is_configurable(client, outbox, resets_db, monkeypatch):
    monkeypatch.setenv("PASSWORD_RESET_EXPIRE_MINUTES", "15")
    issue(client, outbox)
    [stored] = resets_db.all()
    assert datetime.fromisoformat(stored["expires_at"]) - datetime.fromisoformat(stored["created_at"]) == timedelta(minutes=15)
    assert "15 minutos" in outbox[0].text


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "14", "61"])
def test_invalid_link_lifetime_is_refused(monkeypatch, bad):
    monkeypatch.setenv("PASSWORD_RESET_EXPIRE_MINUTES", bad)
    with pytest.raises(RuntimeError):
        get_password_reset_expire_minutes()


def test_frontend_url_comes_from_configuration_never_from_the_request(client, outbox, monkeypatch):
    client.post("/auth/forgot-password", json={"email": BOB}, headers={"Host": "evil.example"})
    assert "evil.example" not in outbox[0].text + outbox[0].html

    monkeypatch.delenv("FRONTEND_URL")
    monkeypatch.delenv("CODESPACE_NAME", raising=False)
    assert get_frontend_url() == "http://localhost:5174"
    monkeypatch.setenv("CODESPACE_NAME", "my-space")
    monkeypatch.setenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")
    assert get_frontend_url() == "https://my-space-5174.app.github.dev"


# --- reset-password --------------------------------------------------------------


def test_reset_sets_the_new_password_and_spends_the_token(client, outbox, resets_db, users_db):
    token = issue(client, outbox)
    response = reset(client, token)
    assert response.status_code == 204 and response.content == b""
    assert login(client, BOB, PASSWORD).status_code == 401
    assert login(client, BOB, NEW_PASSWORD).status_code == 200
    stored = next(d for d in users_db.all() if d["email"] == BOB)
    assert stored["hashed_password"].startswith("$2") and NEW_PASSWORD not in str(stored)
    assert set(stored) == {"id", "email", "hashed_password", "is_active", "role", "created_at"}  # shape untouched

    assert len(resets_db) == 0
    again = reset(client, token, "another-pass-1")
    assert again.status_code == 400 and again.json() == {"detail": "Invalid or expired reset link"}
    assert login(client, BOB, NEW_PASSWORD).status_code == 200


def test_reset_notifies_the_owner_without_the_password(client, outbox):
    reset(client, issue(client, outbox))
    notice = outbox[-1]
    assert len(outbox) == 2 and notice.to == BOB and "ha cambiado" in notice.subject
    assert NEW_PASSWORD not in notice.text + notice.html


def test_reset_only_touches_the_owner_of_the_token(client, outbox):
    reset(client, issue(client, outbox, BOB))
    assert login(client, ALICE, PASSWORD).status_code == 200


def test_unknown_expired_and_malformed_tokens_are_a_uniform_400(client, outbox, resets_db):
    token = issue(client, outbox)
    resets_db.update({"expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
    for bad in (token, "not-a-token", token[:-1] + ("A" if token[-1] != "A" else "B")):
        response = reset(client, bad)
        assert response.status_code == 400 and response.json() == {"detail": "Invalid or expired reset link"}
    assert login(client, BOB, PASSWORD).status_code == 200  # unchanged
    assert len(outbox) == 1  # no "password changed" notice


def test_a_rejected_new_password_does_not_spend_the_token_or_echo_it(client, outbox):
    token = issue(client, outbox)
    for bad in ("abc-12", "é" * 40):
        response = reset(client, token, bad)
        assert response.status_code == 422 and bad not in response.text and token not in response.text
    assert client.post("/auth/reset-password", json={"new_password": NEW_PASSWORD}).status_code == 422
    assert client.post("/auth/reset-password", json={"token": "", "new_password": NEW_PASSWORD}).status_code == 422
    assert reset(client, token).status_code == 204


def test_a_link_dies_when_the_account_is_deactivated_or_deleted(client, outbox, users_db):
    token = issue(client, outbox, BOB)
    users_db.update({"is_active": False}, lambda d: d["email"] == BOB)
    assert reset(client, token).status_code == 400

    users_db.update({"is_active": True}, lambda d: d["email"] == BOB)
    token = issue(client, outbox, ALICE)
    client.delete(f"/users/{uuid_of(ALICE)}", headers=headers_for(ALICE))  # bob is not an admin: stays a 403
    users_db.remove(lambda d: d["email"] == ALICE)
    assert reset(client, token).status_code == 400


def test_a_link_dies_when_the_password_changes_by_another_route(client, outbox):
    token = issue(client, outbox)
    changed = client.put(
        f"/users/{uuid_of(BOB)}", json={"password": "changed-elsewhere", "current_password": PASSWORD}, headers=headers_for(BOB)
    )
    assert changed.status_code == 200
    assert reset(client, token).status_code == 400
    assert login(client, BOB, "changed-elsewhere").status_code == 200


def test_reset_does_not_open_a_session(client, outbox):
    response = reset(client, issue(client, outbox))
    assert "access_token" not in response.text and "set-cookie" not in response.headers


# --- change-password -------------------------------------------------------------


def change(client, email=BOB, current=PASSWORD, new=NEW_PASSWORD, headers=None):
    return client.post(
        "/auth/change-password",
        json={"current_password": current, "new_password": new},
        headers=headers_for(email) if headers is None else headers,
    )


def test_change_password_with_the_current_one(client, outbox, users_db):
    response = change(client)
    assert response.status_code == 204 and response.content == b""
    assert login(client, BOB, PASSWORD).status_code == 401
    assert login(client, BOB, NEW_PASSWORD).status_code == 200
    stored = next(d for d in users_db.all() if d["email"] == BOB)
    assert stored["hashed_password"].startswith("$2") and NEW_PASSWORD not in str(stored)
    [notice] = outbox
    assert notice.to == BOB and "ha cambiado" in notice.subject and NEW_PASSWORD not in notice.text + notice.html


def test_change_password_needs_a_session(client, outbox):
    assert change(client, headers={}).status_code == 401
    assert change(client, headers={"Authorization": "Bearer nope"}).status_code == 401
    assert login(client, BOB, PASSWORD).status_code == 200 and outbox == []


def test_change_password_needs_the_right_current_password(client, outbox):
    wrong = change(client, current="not-my-password")
    assert wrong.status_code == 400 and wrong.json() == {"detail": "Current password is incorrect"}
    assert login(client, BOB, PASSWORD).status_code == 200 and outbox == []


def test_change_password_rejects_the_same_and_invalid_passwords(client, outbox):
    same = change(client, new=PASSWORD)
    assert same.status_code == 422 and "different" in same.json()["detail"]
    for bad in ("abc-12", "é" * 40):
        response = change(client, new=bad)
        assert response.status_code == 422 and bad not in response.text
    assert client.post("/auth/change-password", json={"new_password": NEW_PASSWORD}, headers=headers_for(BOB)).status_code == 422
    assert login(client, BOB, PASSWORD).status_code == 200 and outbox == []


def test_change_password_only_changes_the_session_owner(client):
    assert change(client, BOB).status_code == 204
    assert login(client, ALICE, PASSWORD).status_code == 200


def test_change_password_discards_a_pending_reset_link(client, outbox, resets_db):
    token = issue(client, outbox)
    assert change(client).status_code == 204
    assert len(resets_db) == 0 and reset(client, token, "third-password-1").status_code == 400
    assert login(client, BOB, NEW_PASSWORD).status_code == 200


def test_the_current_session_survives_a_password_change(client):
    """Stateless JWT (no ``iat``, no blacklist): the token in hand keeps working until it expires."""
    headers = headers_for(BOB)
    assert change(client, headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 200


# --- mailer ----------------------------------------------------------------------

MAIL = mailer.Mail(to="bob@example.com", subject="Asunto ñ", text="texto", html="<p>html</p>")


@pytest.fixture()
def real_send(monkeypatch):
    """Undo the autouse outbox: these tests exercise the backends themselves."""
    monkeypatch.setattr(mailer, "send", _REAL_SEND)


_REAL_SEND = mailer.send


def test_console_backend_prints_instead_of_sending(real_send, monkeypatch, capsys):
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)
    mailer.check_settings()
    mailer.send(MAIL)
    printed = capsys.readouterr().out
    assert "To: bob@example.com" in printed and "texto" in printed


def test_smtp_backend_sends_a_multipart_message_over_starttls(real_send, monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            calls.append(("quit",))

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message))

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    for name, value in {
        "EMAIL_BACKEND": "smtp", "EMAIL_FROM": "Nexova <no-reply@nexova.com>", "SMTP_HOST": "smtp.example.com",
        "SMTP_USERNAME": "apikey", "SMTP_PASSWORD": "s3cret",
    }.items():
        monkeypatch.setenv(name, value)
    mailer.check_settings()
    mailer.send(MAIL)

    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send", "quit"]
    assert calls[0] == ("connect", "smtp.example.com", 587) and calls[2] == ("login", "apikey", "s3cret")
    message = calls[3][1]
    assert message["To"] == "bob@example.com" and message["From"] == "Nexova <no-reply@nexova.com>"
    assert message["Subject"] == "Asunto ñ"
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]


def test_resend_backend_posts_to_the_http_api(real_send, monkeypatch):
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout):
        seen["url"], seen["headers"], seen["body"] = request.full_url, dict(request.header_items()), json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("EMAIL_BACKEND", "resend")
    monkeypatch.setenv("EMAIL_FROM", "Nexova <no-reply@nexova.com>")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    mailer.check_settings()
    mailer.send(MAIL)

    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Authorization"] == "Bearer re_test_key"
    assert seen["body"] == {
        "from": "Nexova <no-reply@nexova.com>", "to": ["bob@example.com"], "subject": "Asunto ñ",
        "text": "texto", "html": "<p>html</p>",
    }


@pytest.mark.parametrize(
    "env",
    [
        {"EMAIL_BACKEND": "pigeon"},
        {"EMAIL_BACKEND": "smtp"},
        {"EMAIL_BACKEND": "smtp", "EMAIL_FROM": "a@b.c"},
        {"EMAIL_BACKEND": "smtp", "EMAIL_FROM": "a@b.c", "SMTP_HOST": "h", "SMTP_PORT": "abc"},
        {"EMAIL_BACKEND": "smtp", "EMAIL_FROM": "a@b.c", "SMTP_HOST": "h", "SMTP_SECURITY": "tls13"},
        {"EMAIL_BACKEND": "resend", "EMAIL_FROM": "a@b.c"},
        {"EMAIL_BACKEND": "resend", "RESEND_API_KEY": "re_x"},
    ],
)
def test_a_misconfigured_mailer_is_refused_at_startup(monkeypatch, env):
    for name in ("EMAIL_FROM", "SMTP_HOST", "SMTP_PORT", "SMTP_SECURITY", "RESEND_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(RuntimeError):
        mailer.check_settings()


def test_a_failed_delivery_is_logged_not_raised_and_never_logs_the_body(client, monkeypatch, caplog):
    def boom(mail):
        raise OSError("smtp is down")

    monkeypatch.setattr(mailer, "send", boom)
    response = forgot(client)  # the request still succeeds
    assert response.status_code == 200
    assert "Could not send the email" in caplog.text and "reset-password?token=" not in caplog.text


def test_the_html_part_escapes_the_profile_name(client, outbox, profiles_db):
    profiles_db.update({"name": '<img src=x onerror="alert(1)">'}, lambda d: d["user_id"] == str(uuid_of(BOB)))
    forgot(client)
    assert "<img" not in outbox[0].html and "&lt;img" in outbox[0].html


# --- the reset token is a signed JWT -----------------------------------------------


def test_the_reset_token_is_a_signed_short_lived_jwt(client, outbox):
    from jose import jwt
    from core.config import JWT_ALGORITHM, get_jwt_secret

    token = issue(client, outbox)
    claims = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
    assert set(claims) == {"user_id", "purpose", "jti", "exp"}
    assert claims["user_id"] == str(uuid_of(BOB)) and claims["purpose"] == "password_reset"
    assert claims["exp"] == pytest.approx(datetime.now(timezone.utc).timestamp() + 30 * 60, abs=5)


def test_a_token_signed_with_another_key_is_refused(client, outbox, resets_db):
    from jose import jwt
    from core.config import JWT_ALGORITHM

    issue(client, outbox)
    forged = jwt.encode(
        {"user_id": str(uuid_of(BOB)), "purpose": "password_reset", "jti": "x",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        "k" * 40, algorithm=JWT_ALGORITHM,
    )
    assert reset(client, forged).status_code == 400
    assert login(client, BOB, PASSWORD).status_code == 200


def test_a_session_token_is_not_a_reset_token_and_the_other_way_round(client, outbox):
    from auth.security import create_access_token

    session = create_access_token(uuid_of(BOB))
    assert reset(client, session).status_code == 400  # no ``purpose``
    reset_token = issue(client, outbox)
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {reset_token}"})
    assert me.status_code == 401  # the emailed link must never open a session


def test_a_token_whose_own_expiry_passed_is_refused_even_if_the_store_still_holds_it(client, outbox, resets_db):
    """Isolates the JWT's ``exp``: signature right, hash in the store, store date still in the future."""
    from jose import jwt
    from auth.security import hash_reset_token
    from core.config import JWT_ALGORITHM, get_jwt_secret

    issue(client, outbox)
    expired = jwt.encode(
        {"user_id": str(uuid_of(BOB)), "purpose": "password_reset", "jti": "old",
         "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_jwt_secret(), algorithm=JWT_ALGORITHM,
    )
    resets_db.update({"token_hash": hash_reset_token(expired)})  # the store would accept it
    response = reset(client, expired)
    assert response.status_code == 400 and response.json() == {"detail": "Invalid or expired reset link"}
    assert login(client, BOB, PASSWORD).status_code == 200



def test_a_resend_refusal_is_reported_with_its_reason(real_send, monkeypatch):
    import io
    import urllib.error

    def refuse(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", {}, io.BytesIO(b'{"message":"You can only send testing emails to your own email address"}')
        )

    monkeypatch.setattr(mailer.urllib.request, "urlopen", refuse)
    monkeypatch.setenv("EMAIL_BACKEND", "resend")
    monkeypatch.setenv("EMAIL_FROM", "Nexova <onboarding@resend.dev>")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    with pytest.raises(RuntimeError, match="Resend answered 403.*your own email address") as caught:
        mailer.send(MAIL)
    assert "re_test_key" not in str(caught.value)


def _count_attempts(monkeypatch, outcomes):
    """Replace the real send with a scripted one; returns the list of attempts made."""
    attempts, sleeps = [], []

    def scripted(mail):
        attempts.append(mail)
        outcome = outcomes[min(len(attempts) - 1, len(outcomes) - 1)]
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(mailer, "send", scripted)
    monkeypatch.setattr(mailer.time, "sleep", sleeps.append)
    return attempts, sleeps


def test_a_transient_failure_is_retried_until_it_goes_through(monkeypatch, caplog):
    attempts, sleeps = _count_attempts(monkeypatch, [mailer.TransientMailError("Resend answered 429"), OSError("down"), None])
    mailer.deliver(MAIL)
    assert len(attempts) == 3 and sleeps == [1, 3]
    assert "Could not send" not in caplog.text


def test_a_transient_failure_gives_up_after_three_attempts(monkeypatch, caplog):
    attempts, _ = _count_attempts(monkeypatch, [mailer.TransientMailError("Resend answered 503")])
    mailer.deliver(MAIL)
    assert len(attempts) == 3 and "Could not send the email" in caplog.text


def test_a_definitive_failure_is_not_retried(monkeypatch, caplog):
    attempts, sleeps = _count_attempts(monkeypatch, [RuntimeError("Resend answered 403: domain not verified")])
    mailer.deliver(MAIL)
    assert len(attempts) == 1 and sleeps == [] and "Could not send the email" in caplog.text


def test_resend_429_and_5xx_are_transient_but_403_is_not(real_send, monkeypatch):
    import io
    import urllib.error

    def answering(code):
        def urlopen(request, timeout):
            raise urllib.error.HTTPError(request.full_url, code, "x", {}, io.BytesIO(b"{}"))
        return urlopen

    monkeypatch.setenv("EMAIL_BACKEND", "resend")
    monkeypatch.setenv("EMAIL_FROM", "Nexova <onboarding@resend.dev>")
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    for code, transient in ((429, True), (500, True), (503, True), (403, False), (422, False)):
        monkeypatch.setattr(mailer.urllib.request, "urlopen", answering(code))
        with pytest.raises(RuntimeError) as caught:
            mailer.send(MAIL)
        assert isinstance(caught.value, mailer.TransientMailError) is transient, code


def test_smtp_auth_failure_is_definitive_but_a_4xx_is_transient():
    import smtplib

    assert not mailer._is_transient(smtplib.SMTPAuthenticationError(535, b"bad credentials"))
    assert mailer._is_transient(smtplib.SMTPResponseException(451, b"try again later"))
    assert mailer._is_transient(smtplib.SMTPServerDisconnected("connection lost"))
    assert mailer._is_transient(ConnectionRefusedError())
    assert not mailer._is_transient(ValueError("bug"))
