"""Tests for the server-rendered dashboard endpoint."""

from fastapi.testclient import TestClient

from opsbrief import __version__


def _post_event(client: TestClient, **overrides: object) -> None:
    payload = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": "Ticketing webhook failed",
        "occurred_at": "2026-07-29T14:05:00Z",
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    response = client.post("/events", json=payload)
    assert response.status_code == 201


def test_dashboard_returns_html(client: TestClient) -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text.lstrip().startswith("<!DOCTYPE html>")


def test_dashboard_shows_service_identity(client: TestClient) -> None:
    body = client.get("/dashboard").text

    assert "OpsBrief AI" in body
    assert __version__ in body


def test_dashboard_links_into_the_read_endpoints(client: TestClient) -> None:
    body = client.get("/dashboard").text

    for href in ('href="/brief"', 'href="/risks"', 'href="/events"', 'href="/incidents"'):
        assert href in body


def test_dashboard_renders_without_any_stored_events(client: TestClient) -> None:
    # With no events the recent-events panel shows its empty state rather than a
    # table, and the rest of the page is unaffected.
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "No operational events have been recorded yet." in response.text


def test_dashboard_shows_a_recorded_event(client: TestClient) -> None:
    _post_event(client, subject="Broadcast feed dropped")

    body = client.get("/dashboard").text

    assert "Broadcast feed dropped" in body
    assert "integration.failed" in body
    assert "No operational events have been recorded yet." not in body


def test_dashboard_shows_newest_events_first(client: TestClient) -> None:
    _post_event(client, subject="Earlier event", occurred_at="2026-07-29T09:00:00Z")
    _post_event(client, subject="Later event", occurred_at="2026-07-29T18:00:00Z")

    body = client.get("/dashboard").text

    assert body.index("Later event") < body.index("Earlier event")


def test_dashboard_bounds_the_recent_events_panel(client: TestClient) -> None:
    for minute in range(12):
        _post_event(
            client,
            subject=f"Event {minute:02d}",
            occurred_at=f"2026-07-29T10:{minute:02d}:00Z",
            external_id=f"evt-{minute:02d}",
        )

    body = client.get("/dashboard").text

    # The panel is capped at ten rows, and the caption reports the bounded view.
    assert "Showing the 10 most recent of 12 events." in body
    # The two oldest of the twelve fall outside the ten-row window.
    assert "Event 11" in body
    assert "Event 00" not in body


def test_dashboard_shows_no_active_risks_when_there_are_none(client: TestClient) -> None:
    # A single ordinary event raises no risk, so the risks panel says so.
    _post_event(client, severity="low", status="resolved", subject="All clear")

    body = client.get("/dashboard").text

    assert "No active risks across the stored events." in body


def test_dashboard_shows_a_detected_risk(client: TestClient) -> None:
    # An unresolved event whose deadline is long past is overdue, and overdue work
    # has no recency window, so the risk fires whatever the moment of the request.
    _post_event(
        client,
        source="rostering",
        event_type="task.scheduled",
        subject="Safety inspection for North Stand",
        status="open",
        occurred_at="2020-01-01T09:00:00Z",
        due_at="2020-01-01T18:00:00Z",
        external_id="inspection-1",
    )

    body = client.get("/dashboard").text

    assert "Active risks" in body
    assert "overdue_work rule; source events" in body
    assert "No active risks across the stored events." not in body


def test_dashboard_is_in_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/dashboard" in paths
