"""Assembling the dashboard view from the running service's identity.

The dashboard is a thin server-rendered face over the existing API. This service
gathers what the shell shows: the service identity and the fixed set of links
into the JSON endpoints the later dashboard views render inline. It reads the
settings, not the event store, so it holds no request state and is a pure
function of configuration.
"""

from opsbrief import __version__
from opsbrief.config import Settings
from opsbrief.web import DashboardLink, DashboardView

#: The endpoints the dashboard links into. These are the read surfaces a duty
#: manager reaches for; the later dashboard views (recent events, active risks,
#: the latest brief, incidents) render some of them inline in place of the link.
DASHBOARD_LINKS: tuple[DashboardLink, ...] = (
    DashboardLink(
        label="Daily brief",
        href="/brief",
        description="The current operations brief: a summary and the prioritized risks behind it.",
    ),
    DashboardLink(
        label="Risks",
        href="/risks",
        description="The current risks across all stored events, most urgent first.",
    ),
    DashboardLink(
        label="Events",
        href="/events",
        description="The stored operational events, newest first, filterable and paginated.",
    ),
    DashboardLink(
        label="Incidents",
        href="/incidents",
        description="Tracked incidents, most recently opened first.",
    ),
    DashboardLink(
        label="Health",
        href="/health",
        description="The service status, name, version and environment.",
    ),
    DashboardLink(
        label="API docs",
        href="/docs",
        description="The interactive OpenAPI documentation for every endpoint.",
    ),
)


def build_dashboard_view(settings: Settings) -> DashboardView:
    """Return the view the dashboard shell renders for the running service.

    The identity comes from the settings and the package version; the links are
    the fixed navigation into the existing endpoints. No store is read, so the
    shell renders the same whether or not any events have been recorded.
    """
    return DashboardView(
        service_name=settings.app_name,
        environment=settings.environment,
        version=__version__,
        links=DASHBOARD_LINKS,
    )
