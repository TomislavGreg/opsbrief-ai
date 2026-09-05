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
class NextActionRow:
    """One suggested next action as the dashboard's actions panel shows it.

    Every field is carried straight from the brief's deterministic
    :class:`~opsbrief.brief.actions.NextAction`: the recommended ``action``, the
    ``title`` of the risk it addresses so it reads on its own, its ``severity`` so a
    reader sees how pressing it is, the ``rule`` behind the risk, and the source
    ``event_ids`` the action traces back to. No model takes part.
    """

    action: str
    title: str
    severity: str
    rule: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True)
class TimelineEntryRow:
    """One event of an incident's timeline as the dashboard shows it.

    The fields are the same ones a timeline entry describes an event with, reduced
    to display strings and carried apart from how the panel is rendered. As
    everywhere a person is shown an event, the free-form ``metadata`` is left out.
    ``status`` is empty when the producer stated none.
    """

    occurred_at: str
    source: str
    event_type: str
    subject: str
    severity: str
    status: str


@dataclass(frozen=True)
class IncidentRow:
    """One tracked incident, and its timeline, as the dashboard's panel shows it.

    The header fields (``title``, ``status``, ``severity``, ``opened_at``) come
    straight from the stored incident; ``span`` is a display string for when its
    timeline ran, empty when no cited event resolves. ``entries`` are the
    incident's cited events laid out oldest first, exactly as
    :func:`~opsbrief.incidents.build_incident_timeline` orders them, and
    ``missing_event_ids`` names any cited id no stored event answers to, so a gap
    in the evidence stays visible. No model takes part.
    """

    title: str
    status: str
    severity: str
    opened_at: str
    span: str
    entries: tuple[TimelineEntryRow, ...] = ()
    missing_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class DashboardView:
    """The material the dashboard renders.

    It carries the running service's identity, the latest daily brief, the current
    active risks in priority order, the suggested next actions that address them, the
    tracked incidents with their timelines, a bounded newest-first view of the most
    recent stored events, and the set of links into the JSON endpoints. The brief,
    risks, next-actions, incidents and recent-events panels are rendered inline; the
    remaining links are still presented as navigation, and later views fill them in
    the same way.
    """

    service_name: str
    environment: str
    version: str
    links: tuple[DashboardLink, ...]
    brief: BriefPanel | None = None
    active_risks: tuple[RiskRow, ...] = ()
    next_actions: tuple[NextActionRow, ...] = ()
    incidents: tuple[IncidentRow, ...] = ()
    total_incidents: int = 0
    recent_events: tuple[RecentEventRow, ...] = ()
    total_events: int = 0
