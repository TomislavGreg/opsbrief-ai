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
class BriefPanel:
    """The latest daily brief as the dashboard's brief panel shows it.

    The panel carries the model-phrased ``summary`` alongside the parts that let a
    reader weigh it: the ``model`` that phrased it, the derived ``confidence`` level,
    and the ``notes`` on where the picture is incomplete. The prioritized risks and
    the source references the full brief also holds are shown by the other panels
    and the JSON endpoints, so they are left out here. ``summary`` is empty when the
    provider was unavailable or returned nothing, and the render says so plainly.
    """

    summary: str
    model: str
    confidence: str
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DashboardView:
    """The material the dashboard renders.

    It carries the running service's identity, the latest daily brief, the current
    active risks in priority order, a bounded newest-first view of the most recent
    stored events, and the set of links into the JSON endpoints. The brief, risks
    and recent-events panels are rendered inline; the remaining links are still
    presented as navigation, and later views fill them in the same way.
    """

    service_name: str
    environment: str
    version: str
    links: tuple[DashboardLink, ...]
    brief: BriefPanel | None = None
    active_risks: tuple[RiskRow, ...] = ()
    recent_events: tuple[RecentEventRow, ...] = ()
    total_events: int = 0
