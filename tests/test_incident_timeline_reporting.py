"""Tests for the incident-timeline reporting service."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.events import Event, EventInput
from opsbrief.incidents import Incident, IncidentSeverity
from opsbrief.services import report_incident_timeline
from opsbrief.storage import EventStore, IncidentStore

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def event_store() -> Iterator[EventStore]:
    """Return an event store backed by a throwaway in-memory database."""
    with EventStore.open("sqlite:///:memory:") as store:
        yield store


@pytest.fixture
def incident_store() -> Iterator[IncidentStore]:
    """Return an incident store backed by a throwaway in-memory database."""
    with IncidentStore.open("sqlite:///:memory:") as store:
        yield store


def store_event(store: EventStore, **overrides: object) -> Event:
    """Store one event with sensible defaults and return it."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": "Ticketing webhook failed",
        "occurred_at": (NOW - timedelta(hours=2)).isoformat(),
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    event = Event.from_input(EventInput(**payload))
    store.add(event)
    return event


def test_a_missing_incident_reports_none(
    incident_store: IncidentStore, event_store: EventStore
) -> None:
    timeline = report_incident_timeline(incident_store, event_store, "missing")

    assert timeline is None


def test_timeline_lays_cited_events_out_oldest_first(
    incident_store: IncidentStore, event_store: EventStore
) -> None:
    later = store_event(event_store, occurred_at=(NOW - timedelta(hours=1)).isoformat())
    earlier = store_event(event_store, occurred_at=(NOW - timedelta(hours=3)).isoformat())
    # The incident cites the events in the reverse of the order they occurred, so
    # the timeline has to reorder them rather than echo the citation order.
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=[later.id, earlier.id],
        at=NOW,
    )
    incident_store.add(incident)

    timeline = report_incident_timeline(incident_store, event_store, incident.id)

    assert timeline is not None
    assert timeline.incident_id == incident.id
    assert [entry.id for entry in timeline.entries] == [earlier.id, later.id]
    assert timeline.missing_event_ids == []
    assert timeline.started_at == earlier.occurred_at
    assert timeline.ended_at == later.occurred_at


def test_a_cited_event_with_no_stored_record_is_reported_missing(
    incident_store: IncidentStore, event_store: EventStore
) -> None:
    event = store_event(event_store)
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=[event.id, "gone"],
        at=NOW,
    )
    incident_store.add(incident)

    timeline = report_incident_timeline(incident_store, event_store, incident.id)

    assert timeline is not None
    assert [entry.id for entry in timeline.entries] == [event.id]
    assert timeline.missing_event_ids == ["gone"]
