"""Tests for rendering the dashboard view to HTML."""

from opsbrief.web import (
    BriefPanel,
    DashboardLink,
    DashboardView,
    IncidentRow,
    NextActionRow,
    RecentEventRow,
    RiskRow,
    TimelineEntryRow,
    render_dashboard_page,
)

_BRIEF = BriefPanel(
    summary="One integration keeps failing; deal with the ticketing failures first.",
    model="fake-1",
    confidence="high",
    notes=(),
)

_RISKS = (
    RiskRow(
        title="Integration ticketing has failed 5 times",
        severity="critical",
        rule="repeated_integration_failure",
        event_ids=("e17", "e18", "e19", "e20", "e21"),
    ),
    RiskRow(
        title="Safety inspection for North Stand is overdue",
        severity="high",
        rule="overdue_work",
        event_ids=("e04",),
    ),
)

_ROWS = (
    RecentEventRow(
        occurred_at="2026-07-29 14:05 UTC",
        source="integrations",
        event_type="integration.failed",
        subject="Ticketing webhook failed",
        severity="high",
        status="failed",
    ),
    RecentEventRow(
        occurred_at="2026-07-29 11:30 UTC",
        source="rostering",
        event_type="shift.unfilled",
        subject="Steward shift for fixture 4821 is one short",
        severity="high",
        status="",
    ),
)

_INCIDENTS = (
    IncidentRow(
        title="Ticketing integration failing repeatedly",
        status="investigating",
        severity="high",
        opened_at="2026-07-29 18:00 UTC",
        span="2026-07-29 14:05 UTC to 2026-07-29 14:25 UTC",
        entries=(
            TimelineEntryRow(
                occurred_at="2026-07-29 14:05 UTC",
                source="integrations",
                event_type="integration.failed",
                subject="Ticketing webhook failed",
                severity="high",
                status="failed",
            ),
            TimelineEntryRow(
                occurred_at="2026-07-29 14:25 UTC",
                source="integrations",
                event_type="integration.failed",
                subject="Ticketing webhook failed again",
                severity="high",
                status="",
            ),
        ),
    ),
)

_ACTIONS = (
    NextActionRow(
        action=(
            "Investigate the failing integration and restore it before dependent work is affected."
        ),
        title="Integration ticketing has failed 5 times",
        severity="critical",
        rule="repeated_integration_failure",
        event_ids=("e17", "e18", "e19", "e20", "e21"),
    ),
    NextActionRow(
        action="Escalate the overdue work and agree a new completion time with its owner.",
        title="Safety inspection for North Stand is overdue",
        severity="high",
        rule="overdue_work",
        event_ids=("e04",),
    ),
)

_VIEW = DashboardView(
    service_name="OpsBrief AI",
    environment="production",
    version="1.2.3",
    links=(
        DashboardLink(label="Risks", href="/risks", description="The current risks."),
        DashboardLink(label="Daily brief", href="/brief", description="The daily brief."),
    ),
    brief=_BRIEF,
    active_risks=_RISKS,
    next_actions=_ACTIONS,
    incidents=_INCIDENTS,
    total_incidents=1,
    recent_events=_ROWS,
    total_events=2,
)


def test_page_is_a_complete_html_document() -> None:
    html = render_dashboard_page(_VIEW)

    assert html.lstrip().startswith("<!DOCTYPE html>")
    assert "</html>" in html.rstrip()


def test_page_shows_the_service_identity() -> None:
    html = render_dashboard_page(_VIEW)

    assert "OpsBrief AI" in html
    assert "production" in html
    assert "1.2.3" in html


def test_page_renders_every_link() -> None:
    html = render_dashboard_page(_VIEW)

    assert '<a href="/risks">Risks</a>' in html
    assert '<a href="/brief">Daily brief</a>' in html
    assert "The current risks." in html


def test_dynamic_values_are_escaped() -> None:
    view = DashboardView(
        service_name="OpsBrief <script>",
        environment="dev&prod",
        version="1.0",
        links=(
            DashboardLink(
                label="Events <b>",
                href="/events?source=a&type=b",
                description="Events & more",
            ),
        ),
    )

    html = render_dashboard_page(view)

    assert "<script>" not in html
    assert "OpsBrief &lt;script&gt;" in html
    assert "dev&amp;prod" in html
    assert "Events &lt;b&gt;" in html
    assert "/events?source=a&amp;type=b" in html


def test_page_renders_the_recent_events_panel() -> None:
    html = render_dashboard_page(_VIEW)

    assert "Recent events" in html
    assert "Ticketing webhook failed" in html
    assert "Steward shift for fixture 4821 is one short" in html
    assert "integration.failed" in html
    assert "2026-07-29 14:05 UTC" in html


def test_event_with_no_status_renders_a_placeholder() -> None:
    # The second row has no status; it must not leave an empty cell that reads as
    # a missing column, so a dash stands in for it.
    html = render_dashboard_page(_VIEW)

    assert "&mdash;" in html


def test_empty_store_shows_an_empty_state_not_a_table() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        recent_events=(),
        total_events=0,
    )

    html = render_dashboard_page(view)

    assert "No operational events have been recorded yet." in html
    assert '<table class="events">' not in html


def test_caption_reports_a_bounded_view() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        recent_events=_ROWS,
        total_events=42,
    )

    html = render_dashboard_page(view)

    assert "Showing the 2 most recent of 42 events." in html


def test_recent_event_fields_are_escaped() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        recent_events=(
            RecentEventRow(
                occurred_at="2026-07-29 14:05 UTC",
                source="integrations",
                event_type="integration.failed",
                subject="Broadcast <script>alert(1)</script> feed",
                severity="high",
                status="failed",
            ),
        ),
        total_events=1,
    )

    html = render_dashboard_page(view)

    assert "<script>alert(1)</script>" not in html
    assert "Broadcast &lt;script&gt;" in html


def test_page_renders_the_active_risks_panel() -> None:
    html = render_dashboard_page(_VIEW)

    assert "Active risks" in html
    assert "Integration ticketing has failed 5 times" in html
    assert "Safety inspection for North Stand is overdue" in html
    # Each risk names its rule and cites its source events.
    assert "repeated_integration_failure rule; source events e17, e18, e19, e20, e21" in html
    assert "overdue_work rule; source events e04" in html


def test_risk_severity_is_shown_as_a_badge() -> None:
    html = render_dashboard_page(_VIEW)

    assert "sev-critical" in html
    assert "sev-high" in html


def test_unknown_risk_severity_falls_back_to_a_neutral_badge() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        active_risks=(
            RiskRow(title="Odd risk", severity="unheard-of", rule="some_rule", event_ids=("e1",)),
        ),
    )

    html = render_dashboard_page(view)

    assert "sev-default" in html


def test_no_active_risks_shows_an_empty_state() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        active_risks=(),
    )

    html = render_dashboard_page(view)

    assert "No active risks across the stored events." in html
    assert 'class="risks"' not in html


def test_risk_fields_are_escaped() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        active_risks=(
            RiskRow(
                title="Feed <script>alert(1)</script> failing",
                severity="high",
                rule="repeated_integration_failure",
                event_ids=("e<1>",),
            ),
        ),
    )

    html = render_dashboard_page(view)

    assert "<script>alert(1)</script>" not in html
    assert "Feed &lt;script&gt;" in html
    assert "e&lt;1&gt;" in html


def test_page_renders_the_next_actions_panel() -> None:
    html = render_dashboard_page(_VIEW)

    assert "Suggested next actions" in html
    assert "2 suggested actions, most pressing first." in html
    assert "Investigate the failing integration" in html
    assert "Escalate the overdue work" in html
    # Each action names the risk it addresses and the events it traces to.
    assert "Addresses: Integration ticketing has failed 5 times" in html
    assert "repeated_integration_failure rule" in html
    assert "e17" in html


def test_next_actions_follow_the_risk_priority_order() -> None:
    html = render_dashboard_page(_VIEW)

    assert html.index("Investigate the failing integration") < html.index(
        "Escalate the overdue work"
    )


def test_action_severity_is_shown_as_a_badge() -> None:
    html = render_dashboard_page(_VIEW)

    assert "sev-critical" in html
    assert "sev-high" in html


def test_no_next_actions_shows_an_empty_state() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        next_actions=(),
    )

    html = render_dashboard_page(view)

    assert "Suggested next actions" in html
    assert "No suggested actions: there are no active risks to address." in html


def test_unknown_action_severity_falls_back_to_a_neutral_badge() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        next_actions=(
            NextActionRow(
                action="Review this risk, assign an owner and decide the next step.",
                title="A new kind of risk",
                severity="surprise",
                rule="new_rule",
                event_ids=("e1",),
            ),
        ),
    )

    html = render_dashboard_page(view)

    assert "sev-default" in html
    assert ">surprise</span>" in html


def test_action_fields_are_escaped() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        next_actions=(
            NextActionRow(
                action="Restart <script>alert(1)</script> now",
                title="Feed <b>down</b>",
                severity="high",
                rule="rule&x",
                event_ids=("e<1>",),
            ),
        ),
    )

    html = render_dashboard_page(view)

    assert "<script>alert(1)</script>" not in html
    assert "Restart &lt;script&gt;" in html
    assert "Feed &lt;b&gt;down&lt;/b&gt;" in html
    assert "rule&amp;x" in html
    assert "e&lt;1&gt;" in html


def test_page_renders_the_daily_brief_panel() -> None:
    html = render_dashboard_page(_VIEW)

    assert "Daily brief" in html
    assert "One integration keeps failing" in html
    # The panel names the model that phrased the summary and the confidence level.
    assert "Phrased by fake-1" in html
    assert "conf-high" in html
    assert ">high</span>" in html


def test_brief_notes_are_rendered_when_the_picture_is_incomplete() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        brief=BriefPanel(
            summary="Some risks stand.",
            model="fake-1",
            confidence="medium",
            notes=("Only the most recent events are shown.",),
        ),
    )

    html = render_dashboard_page(view)

    assert "Only the most recent events are shown." in html
    assert "conf-medium" in html


def test_empty_brief_summary_shows_a_placeholder_not_a_blank_line() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        brief=BriefPanel(
            summary="",
            model="fake-1",
            confidence="none",
            notes=("The AI provider was unavailable.",),
        ),
    )

    html = render_dashboard_page(view)

    assert "No summary was phrased for the current picture." in html
    assert "The AI provider was unavailable." in html
    assert "conf-none" in html


def test_unknown_brief_confidence_falls_back_to_a_neutral_badge() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        brief=BriefPanel(summary="A picture.", model="fake-1", confidence="unheard-of"),
    )

    html = render_dashboard_page(view)

    assert "conf-none" in html


def test_brief_summary_is_escaped() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        brief=BriefPanel(
            summary="Feed <script>alert(1)</script> down",
            model="fake<1>",
            confidence="high",
        ),
    )

    html = render_dashboard_page(view)

    assert "<script>alert(1)</script>" not in html
    assert "Feed &lt;script&gt;" in html
    assert "fake&lt;1&gt;" in html


def test_page_without_a_brief_omits_the_panel() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
    )

    html = render_dashboard_page(view)

    assert "Daily brief" not in html


def test_page_renders_the_incidents_panel() -> None:
    html = render_dashboard_page(_VIEW)

    assert "Incidents" in html
    assert "Ticketing integration failing repeatedly" in html
    # The status shows as a badge and the severity reuses the risk severity badge.
    assert "status-investigating" in html
    assert ">investigating</span>" in html
    # The timeline lists the incident's cited events oldest first.
    assert "Ticketing webhook failed" in html
    assert html.index("Ticketing webhook failed") < html.index("Ticketing webhook failed again")
    assert "2026-07-29 14:05 UTC" in html


def test_incident_with_no_resolvable_events_says_so() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        incidents=(
            IncidentRow(
                title="Lost incident",
                status="open",
                severity="medium",
                opened_at="2026-07-29 18:00 UTC",
                span="",
                entries=(),
                missing_event_ids=("gone-1", "gone-2"),
            ),
        ),
        total_incidents=1,
    )

    html = render_dashboard_page(view)

    assert "No cited events are stored for this incident." in html
    assert "Cited events no longer stored: gone-1, gone-2." in html


def test_incidents_panel_reports_a_bounded_view() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        incidents=_INCIDENTS,
        total_incidents=9,
    )

    html = render_dashboard_page(view)

    assert "Showing the 1 most recently opened of 9 incidents." in html


def test_no_incidents_shows_an_empty_state() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        incidents=(),
    )

    html = render_dashboard_page(view)

    assert "No incidents are being tracked." in html
    assert 'class="incidents"' not in html


def test_unknown_incident_status_falls_back_to_a_neutral_badge() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        incidents=(
            IncidentRow(
                title="Odd incident",
                status="unheard-of",
                severity="low",
                opened_at="2026-07-29 18:00 UTC",
                span="",
            ),
        ),
        total_incidents=1,
    )

    html = render_dashboard_page(view)

    assert "status-default" in html


def test_incident_fields_are_escaped() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
        incidents=(
            IncidentRow(
                title="Feed <script>alert(1)</script> down",
                status="open",
                severity="high",
                opened_at="2026-07-29 18:00 UTC",
                span="",
                entries=(
                    TimelineEntryRow(
                        occurred_at="2026-07-29 14:05 UTC",
                        source="integrations",
                        event_type="integration.failed",
                        subject="Broadcast <script>alert(2)</script> feed",
                        severity="high",
                        status="failed",
                    ),
                ),
                missing_event_ids=("e<1>",),
            ),
        ),
        total_incidents=1,
    )

    html = render_dashboard_page(view)

    assert "<script>alert(1)</script>" not in html
    assert "<script>alert(2)</script>" not in html
    assert "Feed &lt;script&gt;" in html
    assert "Broadcast &lt;script&gt;" in html
    assert "e&lt;1&gt;" in html


def test_page_without_incidents_field_shows_the_empty_state() -> None:
    view = DashboardView(
        service_name="OpsBrief AI",
        environment="production",
        version="1.0",
        links=(),
    )

    html = render_dashboard_page(view)

    assert "No incidents are being tracked." in html


def test_rendering_is_pure() -> None:
    assert render_dashboard_page(_VIEW) == render_dashboard_page(_VIEW)
