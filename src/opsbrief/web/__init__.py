"""Server-rendered web surface over the existing API.

The dashboard is a thin, server-rendered view for a person, sitting beside the
JSON API rather than replacing it. It is built from the standard library, with
no template engine and no client-side framework, so it stays small and every
dynamic value is escaped as it is rendered.
"""

from opsbrief.web.render import render_dashboard_page
from opsbrief.web.schema import (
    BriefPanel,
    DashboardLink,
    DashboardView,
    RecentEventRow,
    RiskRow,
)

__all__ = [
    "BriefPanel",
    "DashboardLink",
    "DashboardView",
    "RecentEventRow",
    "RiskRow",
    "render_dashboard_page",
]
