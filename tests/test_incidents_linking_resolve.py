"""Tests for resolving an incident's cited events against stored events."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput
from opsbrief.incidents import (
    Incident,
    IncidentEvents,
    IncidentSeverity,
    resolve_incident_events,
)

NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def make_event(event_id: str, **overrides: object) -> Event:
    """Build a stored event with the given id and fields."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Failure {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def make_incident(event_ids: list[str]) -> Incident:
    """Declare an incident citing the given events."""
    return Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=event_ids,
        at=NOW,
        incident_id="inc-1",
    )


def test_resolving_returns_the_cited_events_in_cited_order() -> None:
    events = [make_event("e1"), make_event("e2"), make_event("e3")]
    incident = make_incident(["e3", "e1"])

    resolved = resolve_incident_events(incident, events)

    assert isinstance(resolved, IncidentEvents)
    assert resolved.incident_id == "inc-1"
    assert [event.id for event in resolved.events] == ["e3", "e1"]
    assert resolved.missing_event_ids == []


def test_events_not_cited_by_the_incident_are_ignored() -> None:
    events = [make_event("e1"), make_event("e2"), make_event("e9")]
    incident = make_incident(["e1"])

    resolved = resolve_incident_events(incident, events)

    assert [event.id for event in resolved.events] == ["e1"]
    assert resolved.missing_event_ids == []


def test_a_cited_event_with_no_stored_record_is_reported_missing() -> None:
    events = [make_event("e1")]
    incident = make_incident(["e1", "e2"])

    resolved = resolve_incident_events(incident, events)

    assert [event.id for event in resolved.events] == ["e1"]
    assert resolved.missing_event_ids == ["e2"]


def test_missing_events_keep_the_cited_order() -> None:
    events = [make_event("e2")]
    incident = make_incident(["e1", "e2", "e3"])

    resolved = resolve_incident_events(incident, events)

    assert [event.id for event in resolved.events] == ["e2"]
    assert resolved.missing_event_ids == ["e1", "e3"]


def test_resolving_against_no_events_reports_every_id_missing() -> None:
    incident = make_incident(["e1", "e2"])

    resolved = resolve_incident_events(incident, [])

    assert resolved.events == []
    assert resolved.missing_event_ids == ["e1", "e2"]


def test_every_cited_id_is_accounted_for_exactly_once() -> None:
    events = [make_event("e1"), make_event("e3")]
    incident = make_incident(["e1", "e2", "e3"])

    resolved = resolve_incident_events(incident, events)

    accounted = [event.id for event in resolved.events] + resolved.missing_event_ids
    assert sorted(accounted) == ["e1", "e2", "e3"]
    assert len(accounted) == len(incident.event_ids)


def test_the_resolved_events_are_the_stored_records() -> None:
    stored = make_event("e1", subject="Ticketing webhook failed again")
    incident = make_incident(["e1"])

    resolved = resolve_incident_events(incident, [stored])

    assert resolved.events[0].subject == "Ticketing webhook failed again"
