"""Tests for rendering the dashboard view to HTML."""

from opsbrief.web import DashboardLink, DashboardView, render_dashboard_page

_VIEW = DashboardView(
    service_name="OpsBrief AI",
    environment="production",
    version="1.2.3",
    links=(
        DashboardLink(label="Risks", href="/risks", description="The current risks."),
        DashboardLink(label="Daily brief", href="/brief", description="The daily brief."),
    ),
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


def test_rendering_is_pure() -> None:
    assert render_dashboard_page(_VIEW) == render_dashboard_page(_VIEW)
