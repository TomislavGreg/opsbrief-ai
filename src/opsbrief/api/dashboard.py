"""The server-rendered dashboard page.

The router stays thin: it reads the settings, hands them to the service that
builds the view, renders it to HTML and returns it. The dashboard is a face for
a person over the same endpoints the JSON API exposes, so it adds no logic of its
own beyond assembling and rendering that view.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from opsbrief.config import get_settings
from opsbrief.services import build_dashboard_view
from opsbrief.web import render_dashboard_page

router = APIRouter(tags=["dashboard"])


@router.get(
    "/dashboard",
    response_class=HTMLResponse,
    summary="Server-rendered operations dashboard",
    response_description="An HTML page linking into the read endpoints.",
)
def read_dashboard() -> HTMLResponse:
    """Return the dashboard shell as an HTML page.

    The page shows the running service's identity and links into the existing
    read endpoints. It is a server-rendered view for a person, built from the
    same settings the API uses, and holds no state of its own.
    """
    view = build_dashboard_view(get_settings())
    return HTMLResponse(render_dashboard_page(view))
