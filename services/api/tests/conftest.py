"""Shared auth fixtures: an isolated user store with three users."""

from __future__ import annotations

import os

os.environ.setdefault("PIPELINE_ENV_FILE", "/nonexistent/.env")  # the pipeline must not read a developer's real services/api/.env in tests
os.environ.setdefault("PIPELINE_RETRIES", "0")  # the pipeline's retry back-off (5/30/120 s) would make failure tests take minutes


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_prefect_results(tmp_path_factory):
    """Keep the results Prefect caches (the pipeline's one-hour cache) in a folder of this test session.

    ``prefect_test_harness`` isolates Prefect's database but NOT its result storage, which defaults to
    ``~/.prefect/storage``: a cached extraction from an earlier session or a demo run would be served to a test whose
    temporary path happens to repeat, and the cache tests would fail depending on what ran before."""
    from prefect.settings import PREFECT_LOCAL_STORAGE_PATH, temporary_settings

    with temporary_settings({PREFECT_LOCAL_STORAGE_PATH: str(tmp_path_factory.mktemp("prefect-results"))}):
        yield

import os
import time
import base64
import json
from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from tinydb import TinyDB

from auth.security import create_access_token, hash_password
from core.config import JWT_ALGORITHM, get_jwt_secret
from profiles import service as profiles_service
from profiles.schemas import Profile
from users import service as users_service
from users.schemas import Role, User

PASSWORD = "correct-horse-battery"
ALICE, BOB, CAROL = "alice@example.com", "bob@example.com", "carol@example.com"
UUIDS = {email: uuid4() for email in (ALICE, BOB, CAROL)}

# bcrypt is deliberately slow: hash once per session, reuse in every test.
_PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(autouse=True)
def users_db(tmp_path, monkeypatch) -> TinyDB:
    """Fresh users (alice, bob, carol) per test, never the real users/db.json."""
    database = TinyDB(tmp_path / "users-db.json")
    for email, user_uuid in UUIDS.items():
        user = User(id=user_uuid, email=email, hashed_password=_PASSWORD_HASH, role=Role.admin if email == ALICE else Role.user)
        database.insert(user.model_dump(mode="json"))
    monkeypatch.setattr(users_service, "_db", database)
    yield database
    database.close()


@pytest.fixture(autouse=True)
def profiles_db(tmp_path, monkeypatch) -> TinyDB:
    """One profile per seeded user, as the app has after startup (default name =
    the local part of the email)."""
    database = TinyDB(tmp_path / "profiles-db.json")
    for email, user_uuid in UUIDS.items():
        database.insert(Profile(user_id=user_uuid, name=email.split("@")[0]).model_dump(mode="json"))
    monkeypatch.setattr(profiles_service, "_db", database)
    yield database
    database.close()


def uuid_of(email: str) -> UUID:
    return UUIDS[email]


def headers_for(email: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(uuid_of(email))}"}


FAR_FUTURE = 4102444800  # year 2100: "not expired" without depending on when the tests run


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def signed_token(claims: dict, key: str | None = None, algorithm: str = JWT_ALGORITHM) -> str:
    """A JWT with exactly these claims, signed with the app's secret unless told otherwise."""
    return jwt.encode(claims, key or get_jwt_secret(), algorithm=algorithm)


def jwt_segment(data: dict) -> str:
    """One base64url JWT segment (header or payload), for building forged tokens by hand."""
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def jwt_payload(segment: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    return headers_for(ALICE)


@pytest.fixture()
def clock(monkeypatch):
    """``clock(seconds)``: from now on the JWT library validates ``exp``/``nbf`` as if ``seconds``
    had passed. Lets a test cross a token's real expiry instant without sleeping. Only the
    validation side moves: tokens are still issued with the real clock."""
    offset = {"seconds": 0}

    class _Meta(type):
        def __instancecheck__(cls, obj):  # jose also uses ``datetime`` for isinstance checks
            return isinstance(obj, datetime)

    class _ShiftedDatetime(metaclass=_Meta):
        @staticmethod
        def now(tz=None):
            return datetime.now(tz) + timedelta(seconds=offset["seconds"])

    monkeypatch.setattr("jose.jwt.datetime", _ShiftedDatetime)

    def travel(seconds: float) -> None:
        offset["seconds"] = seconds

    return travel


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Async tests (``pytestmark = pytest.mark.anyio``) run on asyncio only."""
    return "asyncio"


@pytest.fixture()
async def async_client():
    """``httpx.AsyncClient`` wired straight to the ASGI app (no network, no lifespan). Use it with the
    ``users_db`` / ``profiles_db`` fixtures, which already isolate the stores."""
    from main import app  # imported here so conftest has no import-time side effects

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


@pytest.fixture()
def tokyo_timezone():
    """The server's local timezone is not UTC: ``exp`` is an absolute instant and must not care."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "JST-9"  # POSIX spelling of UTC+9, needs no tz database
    time.tzset()
    yield
    if previous is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = previous
    time.tzset()


@pytest.fixture()
def frozen_clock(monkeypatch):
    """``frozen_clock(timestamp)``: the JWT library validates as if "now" were exactly this POSIX second. For the
    exact edges of ``exp`` / ``nbf``, where the moving ``clock`` fixture is too coarse."""
    now = {"timestamp": 0}

    class _Meta(type):
        def __instancecheck__(cls, obj):
            return isinstance(obj, datetime)

    class _FrozenDatetime(metaclass=_Meta):
        @staticmethod
        def now(tz=None):
            return datetime.fromtimestamp(now["timestamp"], tz)

    monkeypatch.setattr("jose.jwt.datetime", _FrozenDatetime)

    def freeze(timestamp: int) -> None:
        now["timestamp"] = timestamp

    return freeze


@pytest.fixture()
async def authed_client():
    """An ``httpx.AsyncClient`` already logged in as alice (an admin): for the groups of endpoints whose business rules
    are the point of the test, not the session. Use ``async_client`` when the test is about having no session."""
    from main import app  # imported here so conftest has no import-time side effects

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver", headers=headers_for(ALICE)
    ) as client:
        yield client


@pytest.fixture()
def suppliers_db(tmp_path, monkeypatch) -> TinyDB:
    """The 15 seeded suppliers (ids 1 to 15: 8 in Spain, 7 in the USA; Greenhouse and Coursera are suspended) in an isolated
    store, never the real ``suppliers/db.json``."""
    from seed import seed_database
    from suppliers import service as suppliers_service

    database = TinyDB(tmp_path / "suppliers-db.json")
    seed_database(database)
    monkeypatch.setattr(suppliers_service, "_db", database)
    yield database
    database.close()



@pytest.fixture()
def telemetry_db(tmp_path):
    """The telemetry receiver on a throw-away SQLite database, never the real ``inventory/db.sqlite``. Yields the engine."""
    from sqlmodel import Session, SQLModel

    from inventory.database import build_engine, get_db
    from main import app

    engine = build_engine(f"sqlite:///{tmp_path / 'telemetry.sqlite'}")
    SQLModel.metadata.create_all(engine)

    def _session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = _session
    yield engine
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


# ---------------------------------------------------------------- the weekly performance pipeline (shared by its tests)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """The raw and eval files of the pipeline tests go to a temp folder, never to the repo's data/."""
    monkeypatch.setenv("PIPELINE_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"


@pytest.fixture()
def engines(tmp_path):
    """``(source, target)``: a database with demo ``telemetry_events`` and one for the ``reporting`` schema, both throw-away."""
    from data.pipelines.weekly_office_performance import storage
    from data.pipelines.weekly_office_performance.seed_telemetry import seed_telemetry

    source = storage.build_engine(f"sqlite:///{tmp_path / 'telemetry.sqlite'}")
    target = storage.build_engine(f"sqlite:///{tmp_path / 'reporting.sqlite'}")
    seed_telemetry(source)
    storage.create_reporting_schema(target)
    yield source, target
    source.dispose()
    target.dispose()


@pytest.fixture()
def client(engines, auth_headers):
    """An admin's client of the app, with the /reporting endpoints wired to the throw-away ``engines``."""
    from fastapi.testclient import TestClient

    from main import app
    from reporting.database import get_reporting_engine, get_telemetry_engine

    source, target = engines
    app.dependency_overrides[get_telemetry_engine] = lambda: source
    app.dependency_overrides[get_reporting_engine] = lambda: target
    yield TestClient(app, headers=auth_headers)  # ALICE is an admin
    app.dependency_overrides.pop(get_telemetry_engine, None)
    app.dependency_overrides.pop(get_reporting_engine, None)
