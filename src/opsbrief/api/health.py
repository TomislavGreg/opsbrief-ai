"""Health endpoint used by deployments and uptime checks."""

from fastapi import APIRouter
from pydantic import BaseModel

from opsbrief import __version__
from opsbrief.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Reported state of the running service."""

    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Service health")
def read_health() -> HealthResponse:
    """Report that the service is running and which build is deployed."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )
