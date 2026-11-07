"""Operating the pipeline in production: Secret blocks, the deployment with its crons, and the alerts (design, 4.5, 4.6, 8b).

Nothing here talks to a real Slack, a real database or a real Prefect server: the webhook is a throw-away HTTP server on
localhost and the Prefect server is the one of its test harness.

Run:  python -m pytest tests/pipelines/test_operations.py
"""

from __future__ import annotations

import json
import re
import threading
import urllib.request
from datetime import date, datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from data.pipelines import deploy, pipeline
from data.pipelines.weekly_office_performance import alerts, blocks, repository, storage

REPO = Path(__file__).resolve().parents[2]
DESIGN = (REPO / "data" / "pipelines" / "PIPELINE_DESIGN.md").read_text(encoding="utf-8")
WEEK = date(2026, 10, 26)
SECRET_URL = "postgresql://admin:Sup3rS3cret@db.example.com:5432/postgres"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in (alerts.ALERT_URL_ENV, blocks.SECRET_BLOCKS_ENV, "DATABASE_URL", "TELEMETRY_DATABASE_URL", "REPORTING_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------- a webhook on localhost


class Webhook:
    """Records what is posted to it, and answers with ``status``."""

    def __init__(self, status: int = 200):
        self.received: list[dict] = []
        self.headers: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.received.append(json.loads(body))
                outer.headers.append(self.headers["Content-Type"])
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):  # silence
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/hook"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def texts(self) -> list[str]:
        return [m["text"] for m in self.received]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def webhook(monkeypatch):
    hook = Webhook()
    monkeypatch.setenv(alerts.ALERT_URL_ENV, hook.url)
    yield hook
    hook.close()


# ---------------------------------------------------------------- alerts: what is sent, and that nothing can break a run


def test_without_a_webhook_nothing_happens_not_even_a_network_call(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("a network call was made without a webhook"))
    assert alerts.webhook_url() is None
    assert alerts.send_alert("hello") is False
    assert alerts.notify_data_health(WEEK, "production", ["data_health:capture_silent: x"]) is False


def test_the_alert_is_a_post_with_the_slack_compatible_body(webhook):
    assert alerts.send_alert("hola") is True
    assert webhook.received == [{"text": "hola"}] and webhook.headers == ["application/json"]


def test_the_credentials_of_a_connection_url_never_leave_in_an_alert(webhook):
    alerts.send_alert(f"could not connect to {SECRET_URL}: timeout")
    (text,) = webhook.texts
    assert "Sup3rS3cret" not in text and "admin" not in text and "timeout" in text and "db.example.com" in text


def test_a_very_long_message_is_cut(webhook):
    alerts.send_alert("x" * 5000)
    assert len(webhook.texts[0]) == alerts.MAX_TEXT


@pytest.mark.parametrize("status", [400, 404, 500])
def test_a_webhook_that_refuses_the_alert_is_not_an_error(monkeypatch, status):
    hook = Webhook(status)
    monkeypatch.setenv(alerts.ALERT_URL_ENV, hook.url)
    try:
        assert alerts.send_alert("hola") is False
    finally:
        hook.close()


def test_a_webhook_that_is_down_is_not_an_error(monkeypatch):
    hook = Webhook()
    monkeypatch.setenv(alerts.ALERT_URL_ENV, hook.url)
    hook.close()  # nobody is listening any more
    assert alerts.send_alert("hola") is False


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "javascript:alert(1)", "no-scheme"])
def test_only_http_and_https_webhooks_are_used(monkeypatch, url):
    monkeypatch.setenv(alerts.ALERT_URL_ENV, url)
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: pytest.fail("a non-http webhook was opened"))
    assert alerts.send_alert("hola") is False


def test_a_failure_to_send_does_not_write_the_webhook_url_in_the_log(monkeypatch, caplog):
    monkeypatch.setenv(alerts.ALERT_URL_ENV, "http://127.0.0.1:1/T000/B000/SECRETTOKEN")  # port 1: connection refused
    with caplog.at_level("DEBUG"):
        assert alerts.send_alert("hola") is False
    assert "SECRETTOKEN" not in caplog.text


def test_only_the_data_health_notes_become_an_alert(webhook):
    assert alerts.notify_data_health(WEEK, "production", ["save_raw_snapshot: OSError: disk full"]) is False
    assert webhook.received == []  # internal notes about optional steps are noise for the people who read the report
    assert alerts.notify_data_health(WEEK, "production", ["save_raw_snapshot: x", "data_health:capture_silent: no events"]) is True
    (text,) = webhook.texts
    assert "2026-10-26" in text and "production" in text and "capture_silent" in text and "disk full" not in text


def test_the_hooks_say_what_happened_and_for_which_week(webhook):
    run = type("Run", (), {"parameters": {"week_start": "2026-10-26", "environment": "production"}})()
    alerts.notify_failed(None, run, type("State", (), {"message": "ConnectionError: database unreachable"})())
    alerts.notify_crashed(None, run, type("State", (), {"message": "the worker was killed"})())
    failed, crashed = webhook.texts
    assert "NO se ha calculado" in failed and "2026-10-26" in failed and "database unreachable" in failed
    assert "se interrumpió" in crashed and "the worker was killed" in crashed


def test_the_hooks_are_registered_on_the_main_flow():
    flow = pipeline.weekly_office_performance_flow
    assert alerts.notify_failed in flow.on_failure_hooks
    assert alerts.notify_crashed in flow.on_crashed_hooks and pipeline.mark_run_crashed in flow.on_crashed_hooks


# ---------------------------------------------------------------- alerts inside a real run of the flow


@pytest.mark.usefixtures("prefect_runtime")
class TestAlertsInTheFlow:
    def run(self, engines, **kwargs):
        source, target = engines
        return pipeline.weekly_office_performance_flow(week_start=WEEK, source_engine=source, target_engine=target, refresh=True, **kwargs)

    def test_a_healthy_week_sends_nothing(self, engines, webhook):
        assert self.run(engines).state == "Completed"
        assert webhook.received == []

    def test_a_week_with_no_events_at_all_warns_the_people_who_read_the_report(self, engines, webhook, monkeypatch):
        monkeypatch.setattr(repository, "count_window_events", lambda *a, **k: 0)
        assert self.run(engines).state == "Completed"  # the report is still produced
        (text,) = webhook.texts
        assert "capture_silent" in text and "2026-10-26" in text

    def test_a_failed_run_raises_the_alarm_and_still_raises_the_error(self, engines, webhook, monkeypatch):
        monkeypatch.setattr(repository, "extract", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("database unreachable")))
        with pytest.raises(ConnectionError, match="database unreachable"):
            self.run(engines)
        assert len(webhook.texts) == 1 and "NO se ha calculado" in webhook.texts[0] and "database unreachable" in webhook.texts[0]
        assert repository.get_latest_run(engines[1]).state == "Failed"

    def test_a_webhook_that_is_down_never_changes_the_result_of_the_run(self, engines, monkeypatch):
        hook = Webhook()
        monkeypatch.setenv(alerts.ALERT_URL_ENV, hook.url)
        hook.close()
        monkeypatch.setattr(repository, "count_window_events", lambda *a, **k: 0)
        assert self.run(engines).state == "Completed"  # the alert could not be sent; the report is there anyway
        assert repository.get_latest_run(engines[1]).state == "Completed"


# ---------------------------------------------------------------- Secret blocks


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("YES", True), ("on", True), ("0", False), ("", False), ("no", False)])
def test_the_secret_blocks_are_opt_in(monkeypatch, value, expected):
    monkeypatch.setenv(blocks.SECRET_BLOCKS_ENV, value)
    assert blocks.enabled() is expected


def test_without_the_opt_in_the_connection_comes_from_the_environment_exactly_as_before(monkeypatch):
    monkeypatch.setenv("REPORTING_DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setattr(blocks, "load_secret", lambda name: pytest.fail("a block was read without the opt-in"))
    assert storage.database_url("REPORTING_DATABASE_URL") == "postgresql+psycopg2://u:p@h/db"
    assert storage.database_configured() is False  # only a reporting URL: no telemetry database, as before
    monkeypatch.setenv("TELEMETRY_DATABASE_URL", "postgresql://u:p@h/db")
    assert storage.database_configured() is True


def test_the_names_of_the_blocks_are_the_ones_of_the_design():
    assert blocks.DATABASE_BLOCKS == {"TELEMETRY_DATABASE_URL": "telemetry-db-url", "REPORTING_DATABASE_URL": "reporting-db-url"}
    for name in (*blocks.DATABASE_BLOCKS.values(), blocks.ALERT_BLOCK):
        assert f"`{name}`" in DESIGN, f"{name} is not documented in the design"


@pytest.mark.usefixtures("prefect_runtime")
class TestSecretBlocks:
    def test_saving_from_the_environment_returns_names_and_never_values(self):
        saved = blocks.save_from_environment({"DATABASE_URL": SECRET_URL})
        assert saved == ["telemetry-db-url", "reporting-db-url"]  # no webhook was given, so no block for it

    def test_each_block_takes_its_own_variable_before_the_shared_one(self):
        blocks.save_from_environment({"DATABASE_URL": "postgresql://shared/x", "TELEMETRY_DATABASE_URL": "postgresql://read-only/x",
                                      "REPORTING_DATABASE_URL": "postgresql://writer/x", "PIPELINE_ALERT_WEBHOOK_URL": "https://hooks.example.com/x"})
        assert blocks.load_secret("telemetry-db-url") == "postgresql://read-only/x"
        assert blocks.load_secret("reporting-db-url") == "postgresql://writer/x"
        assert blocks.load_secret("pipeline-alert-webhook") == "https://hooks.example.com/x"

    def test_with_the_opt_in_the_url_comes_from_the_block_and_not_from_the_environment(self, monkeypatch):
        blocks.save_from_environment({"DATABASE_URL": "postgresql://from-the-block/x"})
        monkeypatch.setenv("DATABASE_URL", "postgresql://from-the-environment/x")
        monkeypatch.setenv(blocks.SECRET_BLOCKS_ENV, "1")
        assert storage.database_url("REPORTING_DATABASE_URL") == "postgresql+psycopg2://from-the-block/x"
        assert storage.database_url("TELEMETRY_DATABASE_URL") == "postgresql+psycopg2://from-the-block/x"
        assert storage.database_configured() is True

    def test_a_missing_block_stops_with_a_clear_message_and_never_falls_back_to_another_credential(self, monkeypatch):
        monkeypatch.setenv(blocks.SECRET_BLOCKS_ENV, "1")
        monkeypatch.setenv("DATABASE_URL", SECRET_URL)  # a credential IS available in the environment, and must NOT be used
        monkeypatch.setitem(blocks.DATABASE_BLOCKS, "REPORTING_DATABASE_URL", "reporting-db-url-that-does-not-exist")
        with pytest.raises(blocks.SecretBlockError) as error:
            storage.database_url("REPORTING_DATABASE_URL")
        assert "reporting-db-url-that-does-not-exist" in str(error.value) and "Sup3rS3cret" not in str(error.value)

    def test_the_alert_webhook_can_come_from_its_block_and_the_environment_wins(self, monkeypatch):
        blocks.save_from_environment({"PIPELINE_ALERT_WEBHOOK_URL": "https://hooks.example.com/from-the-block"})
        assert alerts.webhook_url() is None  # blocks are off
        monkeypatch.setenv(blocks.SECRET_BLOCKS_ENV, "1")
        assert alerts.webhook_url() == "https://hooks.example.com/from-the-block"
        monkeypatch.setenv(alerts.ALERT_URL_ENV, "https://hooks.example.com/from-the-environment")
        assert alerts.webhook_url() == "https://hooks.example.com/from-the-environment"

    def test_the_command_prints_the_names_it_saved_and_never_a_value(self, monkeypatch, capsys):
        monkeypatch.setenv("DATABASE_URL", SECRET_URL)
        assert blocks.main() == 0
        out = capsys.readouterr()
        assert "telemetry-db-url, reporting-db-url" in out.out and "Sup3rS3cret" not in out.out + out.err

    def test_the_command_refuses_to_save_nothing(self, capsys):
        assert blocks.main() == 1
        assert "nothing to save" in capsys.readouterr().err


# ---------------------------------------------------------------- the deployment and its two crons


def test_the_plan_has_one_deployment_with_the_two_crons_of_the_design_in_utc():
    plan = deploy.plan("nexova-reporting", secret_blocks=False)
    assert plan["name"] == "weekly-office-performance/weekly-office-performance" and plan["work_pool"] == "nexova-reporting"
    assert plan["entrypoint"] == "data/pipelines/pipeline.py:weekly_office_performance_flow"
    monday, thursday = plan["schedules"]
    assert (monday["cron"], monday["timezone"]) == ("0 5 * * 1", "UTC")
    assert (thursday["cron"], thursday["timezone"]) == ("0 5 * * 4", "UTC")
    # both on the last COMPLETE week (no week_start); only the Thursday one ignores the cache, to absorb the late events
    assert monday["parameters"] == {"trigger": "scheduled", "refresh": False}
    assert thursday["parameters"] == {"trigger": "scheduled", "refresh": True}


def test_the_crons_fire_when_the_design_says():
    """Asked to Prefect's own calendar: the next firings after a Saturday are the next Monday and the next Thursday, 05:00 UTC."""
    import asyncio

    from prefect.server.schemas.schedules import CronSchedule

    saturday = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)

    def next_fire(cron: str) -> datetime:
        (fire,) = asyncio.run(CronSchedule(cron=cron, timezone="UTC").get_dates(n=1, start=saturday))
        return fire.astimezone(timezone.utc)

    assert next_fire(deploy.MONDAY) == datetime(2026, 11, 9, 5, tzinfo=timezone.utc)
    assert next_fire(deploy.THURSDAY) == datetime(2026, 11, 12, 5, tzinfo=timezone.utc)


def test_the_crons_of_the_code_are_the_ones_the_design_documents():
    assert f"`{deploy.MONDAY}`" in DESIGN and f"`{deploy.THURSDAY}`" in DESIGN
    assert deploy.TIMEZONE == "UTC"


def test_the_deployment_flow_parameters_exist_in_the_flow():
    """A schedule that passes a parameter the flow does not have would fail every Monday at 05:00."""
    import inspect

    accepted = set(inspect.signature(pipeline.weekly_office_performance_flow.fn).parameters)
    for schedule in deploy.plan("p", False)["schedules"]:
        assert set(schedule["parameters"]) <= accepted


def test_the_runs_read_their_credentials_from_the_blocks_only_when_asked():
    assert deploy.plan("p", False)["job_variables"] == {}
    assert deploy.plan("p", True)["job_variables"] == {"env": {"PIPELINE_SECRET_BLOCKS": "1"}}


def test_the_dry_run_prints_the_plan_and_needs_no_server(capsys):
    assert deploy.main(["--dry-run", "--work-pool", "my-pool", "--secret-blocks"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(json.dumps(deploy.plan("my-pool", True)))


@pytest.mark.usefixtures("prefect_runtime")
def test_the_deployment_is_really_registered_with_its_schedules_in_a_prefect_server():
    """Against the throw-away Prefect server of the test harness: register it, then read it back from the API."""
    from prefect.client.orchestration import get_client
    from prefect.client.schemas.actions import WorkPoolCreate

    with get_client(sync_client=True) as client:
        client.create_work_pool(WorkPoolCreate(name="test-reporting", type="process"))
    deployment_id = deploy.register("test-reporting", secret_blocks=True)
    with get_client(sync_client=True) as client:
        found = client.read_deployment_by_name("weekly-office-performance/weekly-office-performance")
        schedules = {s.slug: s for s in client.read_deployment_schedules(found.id)}
    assert str(found.id) == deployment_id and found.work_pool_name == "test-reporting"
    assert found.entrypoint.endswith("pipeline.py:weekly_office_performance_flow")
    assert set(schedules) == {"monday-scheduled", "thursday-correction"}
    assert schedules["monday-scheduled"].schedule.cron == "0 5 * * 1" and schedules["monday-scheduled"].parameters == {"trigger": "scheduled", "refresh": False}
    assert schedules["thursday-correction"].schedule.cron == "0 5 * * 4" and schedules["thursday-correction"].parameters == {"trigger": "scheduled", "refresh": True}
    assert all(s.schedule.timezone == "UTC" and s.active for s in schedules.values())
    assert found.job_variables == {"env": {"PIPELINE_SECRET_BLOCKS": "1"}}


def test_the_deploy_script_is_runnable_as_a_file_from_any_folder(tmp_path):
    import subprocess
    import sys

    out = subprocess.run([sys.executable, str(REPO / "data" / "pipelines" / "deploy.py"), "--dry-run"], cwd=tmp_path, capture_output=True, text=True,
                         timeout=120, check=False)
    assert out.returncode == 0, out.stderr[-800:]
    assert json.loads(out.stdout)["schedules"][0]["cron"] == "0 5 * * 1"


def test_the_secrets_are_never_in_the_repository():
    """The blocks, the alerts and the deployment hold names and constants, never a URL with a password."""
    for path in (REPO / "data" / "pipelines").rglob("*.py"):
        assert not re.search(r"(postgres(ql)?(\+\w+)?|mysql)://[^\s/@\"']+:[^\s/@\"']+@(?!host|h/|db\.example)", path.read_text(encoding="utf-8")), path


def test_the_readme_explains_why_a_real_database_can_come_out_empty_and_what_the_replacement_does():
    """An empty report from a database whose events are `development` is the filter working: the README says so, with the command."""
    text = (REPO / "data" / "pipelines" / "weekly_office_performance" / "README.md").read_text(encoding="utf-8")
    assert "python data/pipelines/pipeline.py --environment development --week-start 2026-10-26" in text
    assert "**0 filas**" in text and "retira" in text  # the empty result, and the replacement of the week, are both said


@pytest.mark.usefixtures("prefect_runtime")
def test_a_run_of_another_environment_replaces_the_whole_week_as_the_readme_warns(engines):
    """What the README says is real: the table has no environment in its key, so the last run of a week decides its rows."""
    from sqlalchemy import select

    source, target = engines

    def rows() -> int:
        with target.connect() as connection:
            return len(connection.execute(select(storage.weekly_performance)).all())

    run = lambda environment: pipeline.weekly_office_performance_flow(  # noqa: E731
        week_start=WEEK, environment=environment, source_engine=source, target_engine=target, refresh=True)
    assert run("production").state == "Completed" and rows() == 5  # the demo events are `production`
    assert run("development").state == "Completed" and rows() == 0  # this database has none of `development`: the week is replaced by nothing
    assert run("production").state == "Completed" and rows() == 5  # and the last run decides again

