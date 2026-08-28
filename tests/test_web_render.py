"""Tests for rendering the dashboard view to HTML."""

from opsbrief.web import DashboardLink, DashboardView, RecentEventRow, render_dashboard_page

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

_VIEW = DashboardView(
    service_name="OpsBrief AI",
    environment="production",
    version="1.2.3",
    links=(
        DashboardLink(label="Risks", href="/risks", description="The current risks."),
        DashboardLink(label="Daily brief", href="/brief", description="The daily brief."),
    ),
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


def test_rendering_is_pure() -> None:
    assert render_dashboard_page(_VIEW) == render_dashboard_page(_VIEW)
