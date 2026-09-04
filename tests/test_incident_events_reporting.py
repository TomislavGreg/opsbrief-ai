"""Tests for the incident event-linking services."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.incidents import (
    Incident,
    IncidentClosedError,
    IncidentEventLink,
    IncidentSeverity,
    IncidentStatus,
)
from opsbrief.services import link_incident_events, unlink_incident_event
from opsbrief.storage import IncidentStore

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


@pytest.fixture
def store() -> Iterator[IncidentStore]:
    """Return a store backed by a throwaway in-memory database."""
    with IncidentStore.open("sqlite:///:memory:") as store:
        yield store


def declare(store: IncidentStore, event_ids: list[str] | None = None) -> Incident:
    """Declare and store an incident, returning it."""
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=event_ids or ["e17", "e18"],
        at=NOW,
    )
    return store.add(incident)


def test_linking_appends_events_and_persists_them(store: IncidentStore) -> None:
    incident = declare(store)

    linked = link_incident_events(
        store, incident.id, IncidentEventLink(event_ids=["e19", "e20"]), LATER
    )

    assert linked is not None
    assert linked.event_ids == ["e17", "e18", "e19", "e20"]
    assert linked.updated_at == LATER
    assert store.get(incident.id).event_ids == ["e17", "e18", "e19", "e20"]


def test_linking_an_already_cited_event_is_idempotent(store: IncidentStore) -> None:
    incident = declare(store)

    linked = link_incident_events(
        store, incident.id, IncidentEventLink(event_ids=["e18", "e19"]), LATER
    )

    assert linked.event_ids == ["e17", "e18", "e19"]


def test_linking_to_a_missing_incident_returns_none(store: IncidentStore) -> None:
    assert (
        link_incident_events(store, "missing", IncidentEventLink(event_ids=["e19"]), LATER) is None
    )


def test_linking_to_a_closed_incident_is_refused(store: IncidentStore) -> None:
    incident = declare(store)
    store.save(incident.transition_to(IncidentStatus.CLOSED, at=NOW))

    with pytest.raises(IncidentClosedError):
        link_incident_events(store, incident.id, IncidentEventLink(event_ids=["e19"]), LATER)


def test_unlinking_removes_an_event_and_persists_it(store: IncidentStore) -> None:
    incident = declare(store, event_ids=["e17", "e18", "e19"])

    unlinked = unlink_incident_event(store, incident.id, "e18", LATER)

    assert unlinked is not None
    assert unlinked.event_ids == ["e17", "e19"]
    assert unlinked.updated_at == LATER
    assert store.get(incident.id).event_ids == ["e17", "e19"]


def test_unlinking_an_uncited_event_is_idempotent(store: IncidentStore) -> None:
    incident = declare(store)

    unlinked = unlink_incident_event(store, incident.id, "e99", LATER)

    assert unlinked.event_ids == ["e17", "e18"]


def test_unlinking_to_a_missing_incident_returns_none(store: IncidentStore) -> None:
    assert unlink_incident_event(store, "missing", "e17", LATER) is None


def test_unlinking_the_last_event_is_refused(store: IncidentStore) -> None:
    incident = declare(store, event_ids=["e17"])

    with pytest.raises(ValueError):
        unlink_incident_event(store, incident.id, "e17", LATER)


def test_unlinking_from_a_closed_incident_is_refused(store: IncidentStore) -> None:
    incident = declare(store, event_ids=["e17", "e18"])
    store.save(incident.transition_to(IncidentStatus.CLOSED, at=NOW))

    with pytest.raises(IncidentClosedError):
        unlink_incident_event(store, incident.id, "e17", LATER)
