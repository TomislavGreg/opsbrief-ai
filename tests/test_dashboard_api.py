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


def test_dashboard_shows_no_next_actions_when_there_are_no_risks(client: TestClient) -> None:
    # No active risks means nothing to act on, so the next-actions panel says so.
    _post_event(client, severity="low", status="resolved", subject="All clear")

    body = client.get("/dashboard").text

    assert "Suggested next actions" in body
    assert "No suggested actions: there are no active risks to address." in body


def test_dashboard_shows_a_suggested_next_action_for_a_risk(client: TestClient) -> None:
    # The same overdue risk the risks panel shows carries a suggested action, and
    # the next-actions panel names what to do about it, tracing to the same events.
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

    assert "Suggested next actions" in body
    assert "Escalate the overdue work and agree a new completion time with its owner." in body
    assert "Addresses: Safety inspection for North Stand" in body
    assert "No suggested actions: there are no active risks to address." not in body


def test_dashboard_shows_the_daily_brief_panel(client: TestClient) -> None:
    _post_event(client, subject="Broadcast feed dropped")

    body = client.get("/dashboard").text

    # The brief panel is present and names the model that phrased its summary.
    assert "Daily brief" in body
    assert "Phrased by fake-1" in body


def test_dashboard_brief_reports_confidence_on_an_empty_store(client: TestClient) -> None:
    # With no events there is no picture to describe, so the brief's confidence is
    # `none`, and the panel shows that badge rather than omitting the brief.
    body = client.get("/dashboard").text

    assert "Daily brief" in body
    assert "conf-none" in body


def test_dashboard_shows_no_incidents_when_there_are_none(client: TestClient) -> None:
    body = client.get("/dashboard").text

    assert "No incidents are being tracked." in body


def test_dashboard_shows_a_tracked_incident_and_its_timeline(client: TestClient) -> None:
    # Store two events, then declare an incident over them; the panel shows the
    # incident with its cited events laid out oldest first.
    _post_event(
        client,
        subject="Ticketing webhook failed",
        occurred_at="2026-07-29T14:05:00Z",
        external_id="fail-1",
    )
    _post_event(
        client,
        subject="Ticketing webhook failed again",
        occurred_at="2026-07-29T14:25:00Z",
        external_id="fail-2",
    )
    ids = [event["id"] for event in client.get("/events").json()["events"]]
    declared = client.post(
        "/incidents",
        json={
            "title": "Ticketing integration failing repeatedly",
            "severity": "high",
            "event_ids": ids,
        },
    )
    assert declared.status_code == 201

    body = client.get("/dashboard").text

    assert "Incidents" in body
    assert "Ticketing integration failing repeatedly" in body
    assert "No incidents are being tracked." not in body
    # The timeline reads forward in time: the earlier failure before the later one.
    # Each event defaults to status "failed", so its timeline line ends " (failed)".
    assert body.index("Ticketing webhook failed (failed)") < body.index("again (failed)")


def test_dashboard_incident_reports_missing_cited_events(client: TestClient) -> None:
    # An incident may cite an id no stored event answers to; the panel names it as
    # a gap rather than dropping it.
    declared = client.post(
        "/incidents",
        json={
            "title": "Incident over a vanished event",
            "severity": "medium",
            "event_ids": ["not-a-stored-id"],
        },
    )
    assert declared.status_code == 201

    body = client.get("/dashboard").text

    assert "Incident over a vanished event" in body
    assert "No cited events are stored for this incident." in body
    assert "not-a-stored-id" in body


def test_dashboard_is_in_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/dashboard" in paths
