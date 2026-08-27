"""View models for the server-rendered dashboard.

These are plain internal view models, not request or response bodies, so they
are frozen dataclasses rather than Pydantic models: nothing crosses the API
boundary as JSON here. They carry only what the page shows, kept apart from how
it is rendered.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardLink:
    """One navigation link from the dashboard into an existing endpoint."""

    label: str
    href: str
    description: str


@dataclass(frozen=True)
class DashboardView:
    """The material the dashboard shell renders.

    It carries the running service's identity and the set of links into the
    JSON endpoints. Later dashboard views render some of these inline; the shell
    presents them as navigation and states the service it is a face for.
    """

    service_name: str
    environment: str
    version: str
    links: tuple[DashboardLink, ...]
