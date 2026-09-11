from fastapi import FastAPI

from app.routers import health

# One centralized FastAPI app for the whole company — add new domain
# routers here (candidates, vacancies, talent-form submissions, tickets,
# ...) as they're built, rather than spinning up separate services. See
# AGENTS.md § "services/" and ../README.md.
app = FastAPI(title="Nexova API")

app.include_router(health.router)


@app.get("/")
def get_root() -> dict:
    return {"service": "nexova-api", "status": "ok"}
