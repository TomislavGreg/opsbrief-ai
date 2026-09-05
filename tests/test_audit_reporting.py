"""Tests for the generation-audit reporting service."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.ai import FakeAIProvider
from opsbrief.audit import GenerationKind
from opsbrief.events import Event, EventInput
from opsbrief.incidents import Incident, IncidentSeverity
from opsbrief.services import report_brief_audit, report_incident_summary_audit
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


def test_brief_audit_over_an_empty_store_reports_the_gap(event_store: EventStore) -> None:
    audit = report_brief_audit(event_store, NOW, FakeAIProvider(responses=["All quiet."]))

    assert audit.kind is GenerationKind.DAILY_BRIEF
    assert audit.subject_id is None
    assert audit.source_event_ids == []
    assert audit.source_event_count == 0
    assert audit.confidence == "none"
    assert "no_events" in audit.warning_codes


def test_brief_audit_traces_to_the_events_behind_its_risks(event_store: EventStore) -> None:
    overdue = store_event(
        event_store,
        source="tasks",
        event_type="task.update",
        subject="A work item",
        due_at=(NOW - timedelta(hours=2)).isoformat(),
    )

    audit = report_brief_audit(event_store, NOW, FakeAIProvider(responses=["One task is overdue."]))

    assert audit.kind is GenerationKind.DAILY_BRIEF
    assert audit.model == "fake-1"
    assert audit.prompt_version
    assert audit.output_version
    assert overdue.id in audit.source_event_ids
    assert audit.source_event_count == len(audit.source_event_ids)
    assert audit.missing_event_ids == []


def test_incident_audit_names_the_incident_and_its_events(
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

    audit = report_incident_summary_audit(
        incident_store, event_store, incident.id, FakeAIProvider()
    )

    assert audit is not None
    assert audit.kind is GenerationKind.INCIDENT_SUMMARY
    assert audit.subject_id == incident.id
    assert audit.source_event_ids == [event.id]
    assert audit.missing_event_ids == []


def test_incident_audit_carries_a_cited_id_no_event_answers_to(
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

    audit = report_incident_summary_audit(
        incident_store, event_store, incident.id, FakeAIProvider()
    )

    assert audit is not None
    assert audit.source_event_ids == [event.id, "gone"]
    assert audit.missing_event_ids == ["gone"]


def test_a_missing_incident_reports_none(
    incident_store: IncidentStore, event_store: EventStore
) -> None:
    audit = report_incident_summary_audit(incident_store, event_store, "missing", FakeAIProvider())

    assert audit is None
