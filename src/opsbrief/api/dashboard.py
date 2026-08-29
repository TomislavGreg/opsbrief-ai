"""The server-rendered dashboard page.

The router stays thin: it reads the settings, hands them to the service that
builds the view, renders it to HTML and returns it. The dashboard is a face for
a person over the same endpoints the JSON API exposes, so it adds no logic of its
own beyond assembling and rendering that view.
"""

from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from opsbrief.api.dependencies import (
    AIProviderDependency,
    EventStoreDependency,
    ExcludedAIContextFieldsDependency,
    IncidentStoreDependency,
)
from opsbrief.config import get_settings
from opsbrief.services import build_dashboard_view
from opsbrief.web import render_dashboard_page

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    summary="Server-rendered operations dashboard",
    response_description=(
        "An HTML page showing the latest brief, active risks, tracked incidents and "
        "recent events, and linking into the read endpoints."
    ),
)
def read_dashboard(
    store: EventStoreDependency,
    incident_store: IncidentStoreDependency,
    provider: AIProviderDependency,
    excluded_fields: ExcludedAIContextFieldsDependency,
) -> HTMLResponse:
    """Return the dashboard as an HTML page.

    The page shows the running service's identity, the latest daily brief, the
    current active risks in priority order, the tracked incidents with their
    timelines, a bounded newest-first panel of the most recent stored events, and
    links into the remaining read endpoints. The brief is phrased, the risks judged
    and the incident timelines assembled at the moment of the request, the same way
    ``GET /brief``, ``GET /risks`` and ``GET /incidents`` produce them, so the
    dashboard never becomes a second source of truth. It is a server-rendered view for
    a person, built from the same settings, stores and provider the JSON API uses, and
    holds no state of its own.
    """
    view = build_dashboard_view(
        get_settings(),
        store,
        incident_store,
        datetime.now(UTC),
        provider,
        excluded_fields=excluded_fields,
    )
    return HTMLResponse(render_dashboard_page(view))
