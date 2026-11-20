"""Alerts for the people who depend on the report (design, section 8b).

A webhook with a Slack-compatible body (``{"text": "..."}``). It is configured with ``PIPELINE_ALERT_WEBHOOK_URL`` or, with
the Secret blocks on, with the block ``pipeline-alert-webhook``. WITHOUT a configured webhook nothing happens at all: no
network call, no delay, no error.

An alert must never break a run, so everything here is best-effort: a short timeout, no retries, and no exception ever
leaves this module. What is sent contains no credential: connection URLs are redacted and the text is truncated.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse

from data.pipelines.weekly_office_performance import blocks

ALERT_URL_ENV = "PIPELINE_ALERT_WEBHOOK_URL"
TIMEOUT_SECONDS = 5
MAX_TEXT = 600
DATA_HEALTH_PREFIX = "data_health:"

log = logging.getLogger(__name__)
_CREDENTIALS = re.compile(r"([a-z][a-z0-9+.-]*://)[^\s/@]*@", re.IGNORECASE)  # scheme://user:password@host -> scheme://***@host


def redact(text: str) -> str:
    """``text`` without the user and password of any connection URL, and cut to a reasonable size."""
    return _CREDENTIALS.sub(r"\1***@", str(text))[:MAX_TEXT]


def webhook_url() -> str | None:
    """The configured webhook, or ``None``. The environment wins over the block."""
    url = os.environ.get(ALERT_URL_ENV, "").strip()
    if not url and blocks.enabled():
        try:
            url = (blocks.load_secret(blocks.ALERT_BLOCK) or "").strip()
        except Exception:  # noqa: BLE001 - an alert that cannot find its webhook must not break the run
            log.exception("could not read the alert webhook block")
    return url or None


def send_alert(text: str) -> bool:
    """Post ``text`` to the webhook. ``True`` only if it was delivered; never raises."""
    try:
        url = webhook_url()
        if not url:
            return False
        if urlparse(url).scheme not in {"http", "https"}:
            log.warning("the alert webhook is not an http(s) URL: alert not sent")
            return False
        request = urllib.request.Request(
            url, data=json.dumps({"text": redact(text)}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - scheme checked above
            return 200 <= response.status < 300
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        log.warning("alert not sent: %s", type(exc).__name__)  # the exception text could carry the webhook URL
        return False


def _where(flow_run: Any) -> str:
    parameters = getattr(flow_run, "parameters", None) or {}
    week, environment = parameters.get("week_start"), parameters.get("environment")
    return f" (semana {week or 'por defecto'}, entorno {environment or 'por defecto'})"


def notify_failed(flow: Any, flow_run: Any, state: Any) -> None:
    """``on_failure`` hook: the run ended ``Failed`` (its log row already says why)."""
    send_alert(f"El reporte semanal de desempeño NO se ha calculado{_where(flow_run)}: {getattr(state, 'message', None) or 'la corrida falló'}")


def notify_crashed(flow: Any, flow_run: Any, state: Any) -> None:
    """``on_crashed`` hook: the process or its infrastructure died."""
    send_alert(f"El reporte semanal de desempeño se interrumpió{_where(flow_run)}: {getattr(state, 'message', None) or 'el proceso se cayó'}")


def notify_data_health(week_start: Any, environment: str, warnings: Iterable[str]) -> bool:
    """The run completed but says the data may not have been collected (the ``data_health:`` notes). Other warnings are
    internal notes about optional steps and would only be noise: they stay in the run log."""
    notes = [w for w in warnings if w.startswith(DATA_HEALTH_PREFIX)]
    if not notes:
        return False
    return send_alert(f"Aviso sobre los datos del reporte semanal (semana {week_start}, entorno {environment}): " + " | ".join(notes))
