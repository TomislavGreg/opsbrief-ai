"""Health endpoints used by deployments and uptime checks.

``GET /health`` is liveness: it reports that the process is up and which build is
deployed, without touching the database, so it stays cheap and never fails for a
reason outside the process. ``GET /health/ready`` is readiness: it probes the
stores the service depends on and answers 503 when one cannot be reached, so an
orchestrator can gate traffic on a dependency being reachable rather than only on
the process being alive.
"""

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from opsbrief import __version__
from opsbrief.api.dependencies import EventStoreDependency, IncidentStoreDependency
from opsbrief.config import get_settings
from opsbrief.services import Readiness, check_readiness

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Reported state of the running service."""

    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse, summary="Service liveness")
def read_health() -> HealthResponse:
    """Report that the service is running and which build is deployed.

    This is a liveness check: it never touches the database, so it reports only
    that the process is up. Whether the service can actually serve, which depends
    on its stores being reachable, is the readiness check below.
    """
    settings = get_settings()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
    )


@router.get(
    "/health/ready",
    response_model=Readiness,
    summary="Service readiness",
    response_description="Whether every store the service depends on is reachable.",
    responses={503: {"description": "A store the service depends on could not be reached."}},
)
def read_readiness(
    response: Response,
    event_store: EventStoreDependency,
    incident_store: IncidentStoreDependency,
) -> Readiness:
    """Report whether the service's stores are reachable, so traffic can be gated on it.

    Each store is probed with a cheap counting query; the response names whether
    each dependency answered. When every dependency is ready the endpoint answers
    200, and when any is not it answers 503 with the same body, so an orchestrator
    can tell a service that is merely alive from one ready to serve.
    """
    readiness = check_readiness(event_store, incident_store)
    if not readiness.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
