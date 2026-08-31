"""Tests for the incident-summary reporting service."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.ai import CompletionRequest, CompletionResponse, FakeAIProvider
from opsbrief.events import Event, EventInput
from opsbrief.incidents import Incident, IncidentSeverity
from opsbrief.services import report_incident_summary
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
    summary = report_incident_summary(incident_store, event_store, "missing", FakeAIProvider())

    assert summary is None


def test_summary_traces_to_the_incidents_cited_events(
    incident_store: IncidentStore, event_store: EventStore
) -> None:
    event = store_event(event_store)
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=[event.id],
        at=NOW,
    )
    incident_store.add(incident)

    summary = report_incident_summary(
        incident_store,
        event_store,
        incident.id,
        FakeAIProvider(responses=["Ticketing failed and is being investigated."]),
    )

    assert summary is not None
    assert summary.incident_id == incident.id
    assert summary.source_event_ids == [event.id]
    assert summary.missing_event_ids == []
    assert summary.summary == "Ticketing failed and is being investigated."
    assert summary.started_at == event.occurred_at


def test_excluded_fields_are_held_back_from_the_model(
    incident_store: IncidentStore, event_store: EventStore
) -> None:
    event = store_event(event_store, subject="Steward Jane Doe did not report")
    incident = Incident.declare(
        title="Steward shortfall",
        severity=IncidentSeverity.MEDIUM,
        event_ids=[event.id],
        at=NOW,
    )
    incident_store.add(incident)

    class RecordingProvider:
        name = "recording"

        def __init__(self) -> None:
            self.requests: list[CompletionRequest] = []

        def complete(self, request: CompletionRequest) -> CompletionResponse:
            self.requests.append(request)
            return CompletionResponse(text="A summary.", model=self.name)

    provider = RecordingProvider()
    summary = report_incident_summary(
        incident_store,
        event_store,
        incident.id,
        provider,
        excluded_fields=frozenset({"subject"}),
    )

    assert summary is not None
    material = provider.requests[0].input
    assert "Steward Jane Doe did not report" not in material
    assert "[excluded]" in material
