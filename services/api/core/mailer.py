"""Outgoing transactional email. No business logic lives here: callers build a
``Mail`` and hand it over.

The backend is chosen with ``EMAIL_BACKEND``:

- ``console`` (default): prints the message to stdout instead of sending it, so
  development works with no mail account. Never use it in production: the
  reset links end up in the logs.
- ``smtp``: any SMTP relay (every transactional provider offers one), through
  the standard library. ``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USERNAME``,
  ``SMTP_PASSWORD`` and ``SMTP_SECURITY`` (``starttls`` | ``ssl`` | ``none``).
- ``resend``: Resend's HTTP API, with ``RESEND_API_KEY``.

``smtp`` and ``resend`` also need ``EMAIL_FROM``, a sender the provider has verified.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

logger = logging.getLogger(__name__)

BACKENDS = ("console", "smtp", "resend")
SMTP_SECURITY_MODES = ("starttls", "ssl", "none")
DEFAULT_FROM = "Nexova <no-reply@nexova.local>"
RESEND_URL = "https://api.resend.com/emails"
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str


def get_backend() -> str:
    return os.environ.get("EMAIL_BACKEND", "console").strip().lower() or "console"


def get_sender() -> str:
    return os.environ.get("EMAIL_FROM") or DEFAULT_FROM


def _smtp_port() -> int:
    raw = os.environ.get("SMTP_PORT", "587")
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError("SMTP_PORT must be an integer") from None


def _smtp_security() -> str:
    return os.environ.get("SMTP_SECURITY", "starttls").strip().lower()


def check_settings() -> None:
    """Called at startup: a misconfigured mailer stops the API there, instead of
    failing silently the first time somebody forgets a password."""
    backend = get_backend()
    if backend not in BACKENDS:
        raise RuntimeError(f"EMAIL_BACKEND must be one of {', '.join(BACKENDS)}")
    if backend == "console":
        logger.warning("EMAIL_BACKEND is 'console': emails are printed to stdout, not sent")
        return
    required = ["EMAIL_FROM", "SMTP_HOST"] if backend == "smtp" else ["EMAIL_FROM", "RESEND_API_KEY"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"EMAIL_BACKEND={backend} needs {', '.join(missing)}")
    if backend == "smtp":
        _smtp_port()
        if _smtp_security() not in SMTP_SECURITY_MODES:
            raise RuntimeError(f"SMTP_SECURITY must be one of {', '.join(SMTP_SECURITY_MODES)}")


def send(mail: Mail) -> None:
    """Send through the configured backend. Raises if the provider refuses."""
    backend = get_backend()
    if backend == "smtp":
        _send_smtp(mail)
    elif backend == "resend":
        _send_resend(mail)
    else:
        _send_console(mail)


def deliver(mail: Mail) -> None:
    """``send`` for background tasks: a failure is logged, never raised (the HTTP
    response is already gone). The body is not logged: it may carry a reset link."""
    try:
        send(mail)
    except Exception:
        logger.exception("Could not send the email %r", mail.subject)


def _send_console(mail: Mail) -> None:
    print(
        f"\n----- email (EMAIL_BACKEND=console, not sent) -----\n"
        f"From: {get_sender()}\nTo: {mail.to}\nSubject: {mail.subject}\n\n{mail.text}\n"
        f"----------------------------------------------------\n",
        flush=True,
    )


def _send_smtp(mail: Mail) -> None:
    message = EmailMessage()
    message["From"] = get_sender()
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid()
    message.set_content(mail.text)
    message.add_alternative(mail.html, subtype="html")

    host, port, security = os.environ["SMTP_HOST"], _smtp_port(), _smtp_security()
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_SECONDS, context=context)
    else:
        client = smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS)
    with client:
        if security == "starttls":
            client.starttls(context=context)
        username = os.environ.get("SMTP_USERNAME")
        if username:
            client.login(username, os.environ.get("SMTP_PASSWORD", ""))
        client.send_message(message)


def _send_resend(mail: Mail) -> None:
    payload = {"from": get_sender(), "to": [mail.to], "subject": mail.subject, "text": mail.text, "html": mail.html}
    request = urllib.request.Request(
        RESEND_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
            "Content-Type": "application/json",
            "User-Agent": "nexova-api",  # the default urllib agent is rejected by Resend's edge
        },
        method="POST",
    )
    # urlopen raises HTTPError on a 4xx/5xx, which is what ``deliver`` logs.
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        response.read()
