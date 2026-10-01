"""Nexova centralized backend API — single FastAPI app, one router per
domain (see docs/ARCHITECTURE_PROPOSAL.md for the reasoning).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from auth.router import router as auth_router
from core import mailer
from core.config import get_allowed_origins, get_jwt_secret, get_password_reset_expire_minutes
from core.errors import validation_error_handler
from incidents.router import router as incidents_router
from profiles import service as profiles_service
from profiles.router import router as profiles_router
from suppliers.router import router as suppliers_router
from users import service as users_service
from users.router import public_router as users_public_router
from users.router import router as users_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_jwt_secret()  # fail at startup, not on the first login, if SECRET_KEY is invalid
    get_password_reset_expire_minutes()  # same for the reset-link lifetime and the mailer
    mailer.check_settings()
    users_service.bootstrap_first_user()
    users_service.migrate_legacy_users()
    profiles_service.migrate_legacy_profiles()
    users_service.sync_profiles()
    yield


app = FastAPI(title="Nexova API", lifespan=lifespan)
app.add_exception_handler(RequestValidationError, validation_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=False,  # auth is a Bearer JWT in the Authorization header: no cookies
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public: login (which is how a session starts), sign-up (POST /users), the
# forgotten-password pair (POST /auth/forgot-password, /auth/reset-password) and
# the liveness check below.
# Everything else is protected inside its own router.
app.include_router(auth_router, prefix="/auth")
app.include_router(users_router, prefix="/users")
app.include_router(users_public_router, prefix="/users")
app.include_router(profiles_router, prefix="/profiles")
app.include_router(incidents_router)
app.include_router(suppliers_router, prefix="/suppliers")
app.include_router(suppliers_router, prefix="/api/suppliers", include_in_schema=False)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
