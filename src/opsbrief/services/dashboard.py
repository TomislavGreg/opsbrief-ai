"""Assembling the dashboard view from the running service and its events.

The dashboard is a thin server-rendered face over the existing API. This service
gathers what the page shows: the service identity, the current active risks in
priority order, a bounded newest-first view of the most recent stored events, and
the fixed set of links into the JSON endpoints the later dashboard views render
inline. The identity comes from the settings; the risks and recent events come
from the event store, computed and read the same way the ``GET /risks`` and
``GET /events`` endpoints compute and read them.
"""

from collections.abc import Container
from datetime import datetime

from opsbrief import __version__
from opsbrief.ai import AIProvider
from opsbrief.brief import DailyBrief
from opsbrief.config import Settings
from opsbrief.events import Event
from opsbrief.risks import Risk
from opsbrief.services.brief_reporting import report_daily_brief
from opsbrief.services.risk_reporting import list_risks
from opsbrief.storage import EventStore
from opsbrief.web import BriefPanel, DashboardLink, DashboardView, RecentEventRow, RiskRow

#: How many recent events the dashboard panel shows. The view is bounded so the
#: page stays small no matter how much history the store holds; the full,
#: filterable listing remains a click away at ``GET /events``.
DEFAULT_DASHBOARD_RECENT_EVENTS = 10

#: The endpoints the dashboard links into. These are the read surfaces a duty
#: manager reaches for; the recent-events panel is now rendered inline, and the
#: later dashboard views (active risks, the latest brief, incidents) render some
#: of the rest inline in place of their link.
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
        label="All events",
        href="/events",
        description="Every stored operational event, newest first, filterable and paginated.",
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


def _format_instant(value: datetime) -> str:
    """Render a stored UTC instant for display, to the minute.

    Timestamps are stored in UTC, so the label is unambiguous without carrying an
    offset; seconds are dropped because a duty manager reads the panel at a glance.
    """
    return value.strftime("%Y-%m-%d %H:%M UTC")


def _recent_event_row(event: Event) -> RecentEventRow:
    """Reduce a stored event to the row the dashboard panel shows it as.

    Only the fields a person reads at a glance are carried, as display strings;
    the free-form ``metadata`` is left out, exactly as it is from a brief digest
    or a timeline entry, so nothing sensitive reaches the page.
    """
    return RecentEventRow(
        occurred_at=_format_instant(event.occurred_at),
        source=event.source,
        event_type=event.event_type,
        subject=event.subject,
        severity=event.severity.value,
        status=event.status.value if event.status is not None else "",
    )


def _brief_panel(brief: DailyBrief) -> BriefPanel:
    """Reduce a generated daily brief to the panel the dashboard shows it as.

    Only the parts the panel presents are carried: the model-phrased ``summary``,
    the ``model`` that phrased it, the derived ``confidence`` level and the ``notes``
    on where the picture is incomplete. The prioritized risks and source references
    the brief also holds are shown by the other panels and the JSON endpoints, so
    they are not duplicated here. No model takes part in this reduction.
    """
    return BriefPanel(
        summary=brief.summary,
        model=brief.model,
        confidence=brief.confidence.value,
        notes=tuple(brief.notes),
    )


def _risk_row(risk: Risk) -> RiskRow:
    """Reduce a detected risk to the row the dashboard panel shows it as.

    Every field is the rule's own output, carried through unchanged, so the panel
    names the rule and the source events behind each risk exactly as ``GET /risks``
    does. No model takes part.
    """
    return RiskRow(
        title=risk.title,
        severity=risk.severity.value,
        rule=risk.rule,
        event_ids=tuple(risk.event_ids),
    )


def build_dashboard_view(
    settings: Settings,
    store: EventStore,
    now: datetime,
    provider: AIProvider,
    *,
    recent_limit: int = DEFAULT_DASHBOARD_RECENT_EVENTS,
    excluded_fields: Container[str] = frozenset(),
) -> DashboardView:
    """Return the view the dashboard renders for the running service.

    The identity comes from the settings and the package version. The daily-brief
    panel is the current brief across the whole event history at ``now``, phrased by
    ``provider`` the same way ``GET /brief`` phrases it, with ``excluded_fields`` held
    back from the material the model is shown; only its summary comes from the model,
    and a provider outage degrades to the deterministic picture rather than failing
    the page. The active-risks panel runs the canonical rule set over the whole
    history at ``now`` and ranks the result most urgent first, the same way
    ``GET /risks`` does. The recent-events panel is the ``recent_limit`` most recently
    occurred events, newest first, read from ``store`` the same way the ``GET /events``
    listing reads it, alongside the total number of stored events so the panel can say
    when it is showing a bounded view. On an empty store the risks and recent-events
    panels are empty and the brief reports an empty picture.
    """
    if recent_limit < 1:
        raise ValueError("recent_limit must be at least 1")

    brief = report_daily_brief(store, now, provider, excluded_fields=excluded_fields)
    risks = list_risks(store, now).risks
    recent = store.list_events(limit=recent_limit)
    total = store.count()
    return DashboardView(
        service_name=settings.app_name,
        environment=settings.environment,
        version=__version__,
        links=DASHBOARD_LINKS,
        brief=_brief_panel(brief),
        active_risks=tuple(_risk_row(risk) for risk in risks),
        recent_events=tuple(_recent_event_row(event) for event in recent),
        total_events=total,
    )
