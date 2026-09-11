from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> dict:
    """Liveness check — confirms the API process is up and responding."""
    return {"status": "ok"}
