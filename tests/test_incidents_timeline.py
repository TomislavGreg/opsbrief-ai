"""Tests for assembling an incident's timeline from stored events."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventSeverity, EventStatus
from opsbrief.incidents import (
    Incident,
    IncidentSeverity,
    IncidentTimeline,
    TimelineEntry,
    build_incident_timeline,
)

NOW = datetime(2026, 8, 13, 18, 0, tzinfo=UTC)


def make_event(event_id: str, *, minutes_ago: int = 0, **overrides: object) -> Event:
    """Build a stored event with the given id and occurrence time."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Failure {event_id}",
        "occurred_at": NOW - timedelta(minutes=minutes_ago),
        "severity": "high",
        "status": "failed",
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


def test_entries_are_ordered_oldest_first_regardless_of_cited_order() -> None:
    events = [
        make_event("e1", minutes_ago=10),
        make_event("e2", minutes_ago=90),
        make_event("e3", minutes_ago=50),
    ]
    incident = make_incident(["e1", "e2", "e3"])

    timeline = build_incident_timeline(incident, events)

    assert isinstance(timeline, IncidentTimeline)
    assert timeline.incident_id == "inc-1"
    assert [entry.id for entry in timeline.entries] == ["e2", "e3", "e1"]
    assert timeline.missing_event_ids == []


def test_ties_on_occurrence_are_broken_by_event_id() -> None:
    events = [
        make_event("e3", minutes_ago=30),
        make_event("e1", minutes_ago=30),
        make_event("e2", minutes_ago=30),
    ]
    incident = make_incident(["e3", "e2", "e1"])

    timeline = build_incident_timeline(incident, events)

    assert [entry.id for entry in timeline.entries] == ["e1", "e2", "e3"]


def test_a_cited_event_with_no_stored_record_is_reported_missing() -> None:
    events = [make_event("e1", minutes_ago=20)]
    incident = make_incident(["e1", "e2"])

    timeline = build_incident_timeline(incident, events)

    assert [entry.id for entry in timeline.entries] == ["e1"]
    assert timeline.missing_event_ids == ["e2"]


def test_missing_ids_keep_the_cited_order() -> None:
    events = [make_event("e2", minutes_ago=20)]
    incident = make_incident(["e3", "e2", "e1"])

    timeline = build_incident_timeline(incident, events)

    assert [entry.id for entry in timeline.entries] == ["e2"]
    assert timeline.missing_event_ids == ["e3", "e1"]


def test_every_cited_id_is_accounted_for_exactly_once() -> None:
    events = [make_event("e1", minutes_ago=10), make_event("e3", minutes_ago=30)]
    incident = make_incident(["e1", "e2", "e3"])

    timeline = build_incident_timeline(incident, events)

    accounted = [entry.id for entry in timeline.entries] + timeline.missing_event_ids
    assert sorted(accounted) == ["e1", "e2", "e3"]
    assert len(accounted) == len(incident.event_ids)


def test_events_not_cited_by_the_incident_are_ignored() -> None:
    events = [
        make_event("e1", minutes_ago=10),
        make_event("e9", minutes_ago=5),
    ]
    incident = make_incident(["e1"])

    timeline = build_incident_timeline(incident, events)

    assert [entry.id for entry in timeline.entries] == ["e1"]
    assert timeline.missing_event_ids == []


def test_an_entry_carries_the_event_fields_a_timeline_describes() -> None:
    stored = make_event(
        "e1",
        minutes_ago=15,
        source="rostering",
        event_type="shift.unfilled",
        subject="Steward shift is one short",
        severity="medium",
        status="open",
    )
    incident = make_incident(["e1"])

    entry = build_incident_timeline(incident, [stored]).entries[0]

    assert isinstance(entry, TimelineEntry)
    assert entry.id == "e1"
    assert entry.source == "rostering"
    assert entry.event_type == "shift.unfilled"
    assert entry.subject == "Steward shift is one short"
    assert entry.occurred_at == stored.occurred_at
    assert entry.severity is EventSeverity.MEDIUM
    assert entry.status is EventStatus.OPEN


def test_an_entry_does_not_carry_event_metadata() -> None:
    stored = make_event("e1", minutes_ago=15, metadata={"attempts": 5})
    incident = make_incident(["e1"])

    entry = build_incident_timeline(incident, [stored]).entries[0]

    assert "metadata" not in entry.model_dump()


def test_the_span_runs_from_the_first_event_to_the_last() -> None:
    events = [
        make_event("e1", minutes_ago=10),
        make_event("e2", minutes_ago=90),
        make_event("e3", minutes_ago=50),
    ]
    incident = make_incident(["e1", "e2", "e3"])

    timeline = build_incident_timeline(incident, events)

    assert timeline.started_at == NOW - timedelta(minutes=90)
    assert timeline.ended_at == NOW - timedelta(minutes=10)


def test_a_single_event_timeline_starts_and_ends_at_that_event() -> None:
    stored = make_event("e1", minutes_ago=20)
    incident = make_incident(["e1"])

    timeline = build_incident_timeline(incident, [stored])

    assert timeline.started_at == stored.occurred_at
    assert timeline.ended_at == stored.occurred_at


def test_a_timeline_with_no_resolved_events_has_no_span() -> None:
    incident = make_incident(["e1", "e2"])

    timeline = build_incident_timeline(incident, [])

    assert timeline.entries == []
    assert timeline.missing_event_ids == ["e1", "e2"]
    assert timeline.started_at is None
    assert timeline.ended_at is None


def test_building_a_timeline_does_not_mutate_the_incident() -> None:
    events = [make_event("e1", minutes_ago=10), make_event("e2", minutes_ago=90)]
    incident = make_incident(["e1", "e2"])

    build_incident_timeline(incident, events)

    assert incident.event_ids == ["e1", "e2"]
