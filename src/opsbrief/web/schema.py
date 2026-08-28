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
class RecentEventRow:
    """One stored event as the dashboard's recent-events panel shows it.

    The fields are the same ones a brief digest or a timeline entry describes an
    event with, reduced to display strings and carried apart from how the panel
    is rendered. The free-form ``metadata`` is left out, as it is everywhere a
    person is shown an event, so nothing sensitive reaches the page. ``status``
    is empty when the producer stated none.
    """

    occurred_at: str
    source: str
    event_type: str
    subject: str
    severity: str
    status: str


@dataclass(frozen=True)
class RiskRow:
    """One active risk as the dashboard's risks panel shows it.

    Every field is the rule's own deterministic output, carried straight from the
    detected :class:`~opsbrief.risks.schema.Risk`: the ``rule`` that raised it, its
    one-line ``title``, its ``severity``, and the source ``event_ids`` behind it so
    the panel stays traceable to the evidence. No model takes part.
    """

    title: str
    severity: str
    rule: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True)
class DashboardView:
    """The material the dashboard renders.

    It carries the running service's identity, the current active risks in
    priority order, a bounded newest-first view of the most recent stored events,
    and the set of links into the JSON endpoints. The risks and recent-events
    panels are rendered inline; the remaining links are still presented as
    navigation, and later views fill them in the same way.
    """

    service_name: str
    environment: str
    version: str
    links: tuple[DashboardLink, ...]
    active_risks: tuple[RiskRow, ...] = ()
    recent_events: tuple[RecentEventRow, ...] = ()
    total_events: int = 0
