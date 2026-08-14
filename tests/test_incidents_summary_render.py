"""Tests for rendering an incident and its timeline as summary material."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput
from opsbrief.incidents import (
    Incident,
    IncidentSeverity,
    build_incident_timeline,
)
from opsbrief.incidents.summary import render_incident_material

NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


def make_event(event_id: str, *, minutes_ago: int = 0, **overrides: object) -> Event:
    """Build a stored event with the given id and occurrence time."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Ticketing webhook failed ({event_id})",
        "occurred_at": NOW - timedelta(minutes=minutes_ago),
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def make_incident(event_ids: list[str], **overrides: object) -> Incident:
    """Declare an incident citing the given events."""
    payload: dict[str, object] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": IncidentSeverity.HIGH,
        "event_ids": event_ids,
        "at": NOW,
        "incident_id": "inc-1",
    }
    payload.update(overrides)
    return Incident.declare(**payload)


def test_render_lists_the_incident_details_and_its_timeline() -> None:
    events = [make_event("e1", minutes_ago=90), make_event("e2", minutes_ago=10)]
    incident = make_incident(["e2", "e1"])

    rendered = render_incident_material(incident, build_incident_timeline(incident, events))

    assert "Incident: Ticketing integration failing repeatedly" in rendered
    assert "Status: open" in rendered
    assert "Severity: high" in rendered
    assert "Timeline (oldest first):" in rendered
    # Oldest event is rendered before the newer one.
    assert rendered.index("e1") < rendered.index("e2")
    assert "integrations integration.failed" in rendered


def test_render_states_the_span_from_the_timeline() -> None:
    events = [make_event("e1", minutes_ago=90), make_event("e2", minutes_ago=10)]
    incident = make_incident(["e1", "e2"])

    rendered = render_incident_material(incident, build_incident_timeline(incident, events))

    started = (NOW - timedelta(minutes=90)).isoformat()
    ended = (NOW - timedelta(minutes=10)).isoformat()
    assert f"Span: {started} to {ended}" in rendered


def test_render_notes_cited_events_that_no_longer_resolve() -> None:
    events = [make_event("e1", minutes_ago=20)]
    incident = make_incident(["e1", "e2"])

    rendered = render_incident_material(incident, build_incident_timeline(incident, events))

    assert "1 cited event(s) no longer resolve" in rendered


def test_render_says_none_when_no_events_resolve() -> None:
    incident = make_incident(["e1", "e2"])

    rendered = render_incident_material(incident, build_incident_timeline(incident, []))

    assert "Timeline (oldest first): none." in rendered
    assert "no cited events resolved" in rendered
