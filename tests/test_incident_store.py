"""Tests for SQLite incident persistence."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.incidents import Incident, IncidentSeverity, IncidentStatus
from opsbrief.storage import (
    DuplicateIncidentIdError,
    IncidentNotFoundError,
    IncidentStore,
)

OPENED_AT = datetime(2026, 7, 29, 9, 30, tzinfo=UTC)


@pytest.fixture
def store() -> Iterator[IncidentStore]:
    """Return a store backed by a throwaway in-memory database."""
    with IncidentStore.open("sqlite:///:memory:") as store:
        yield store


def make_incident(
    *,
    incident_id: str = "inc-1",
    title: str = "Ticketing integration failing repeatedly",
    severity: IncidentSeverity = IncidentSeverity.HIGH,
    event_ids: list[str] | None = None,
    at: datetime = OPENED_AT,
) -> Incident:
    """Return a freshly declared incident."""
    return Incident.declare(
        title=title,
        severity=severity,
        event_ids=event_ids or ["e17", "e18", "e19"],
        at=at,
        incident_id=incident_id,
    )


def test_declared_incident_round_trips(store: IncidentStore) -> None:
    incident = make_incident()

    store.add(incident)

    assert store.get(incident.id) == incident


def test_inactive_incident_round_trips(store: IncidentStore) -> None:
    resolved = make_incident().transition_to(
        IncidentStatus.RESOLVED, at=OPENED_AT + timedelta(hours=2)
    )

    store.add(resolved)
    stored = store.get(resolved.id)

    assert stored == resolved
    assert stored is not None
    assert stored.status is IncidentStatus.RESOLVED
    assert stored.resolved_at == OPENED_AT + timedelta(hours=2)
    assert stored.is_active is False


def test_event_id_order_is_preserved(store: IncidentStore) -> None:
    incident = make_incident(event_ids=["e30", "e10", "e20"])

    store.add(incident)
    stored = store.get(incident.id)

    assert stored is not None
    assert stored.event_ids == ["e30", "e10", "e20"]


def test_get_returns_none_for_unknown_id(store: IncidentStore) -> None:
    assert store.get("missing") is None


def test_add_rejects_a_duplicate_id(store: IncidentStore) -> None:
    store.add(make_incident())

    with pytest.raises(DuplicateIncidentIdError):
        store.add(make_incident(title="A different incident under the same id"))


def test_save_persists_a_transition(store: IncidentStore) -> None:
    incident = make_incident()
    store.add(incident)

    investigating = incident.transition_to(
        IncidentStatus.INVESTIGATING, at=OPENED_AT + timedelta(minutes=15)
    )
    store.save(investigating)

    assert store.get(incident.id) == investigating


def test_save_persists_linked_events(store: IncidentStore) -> None:
    incident = make_incident()
    store.add(incident)

    linked = incident.link_events(["e20", "e21"], at=OPENED_AT + timedelta(minutes=5))
    store.save(linked)
    stored = store.get(incident.id)

    assert stored is not None
    assert stored.event_ids == ["e17", "e18", "e19", "e20", "e21"]


def test_save_rejects_an_unstored_incident(store: IncidentStore) -> None:
    with pytest.raises(IncidentNotFoundError):
        store.save(make_incident())


def test_list_returns_most_recently_opened_first(store: IncidentStore) -> None:
    older = make_incident(incident_id="inc-old", at=OPENED_AT)
    newer = make_incident(incident_id="inc-new", at=OPENED_AT + timedelta(hours=1))
    store.add(older)
    store.add(newer)

    listed = store.list_incidents()

    assert [incident.id for incident in listed] == ["inc-new", "inc-old"]


def test_list_filters_by_status(store: IncidentStore) -> None:
    store.add(make_incident(incident_id="inc-open"))
    resolved = make_incident(incident_id="inc-resolved").transition_to(
        IncidentStatus.RESOLVED, at=OPENED_AT + timedelta(hours=1)
    )
    store.add(resolved)

    listed = store.list_incidents(status=IncidentStatus.RESOLVED)

    assert [incident.id for incident in listed] == ["inc-resolved"]


def test_list_pages_through_matches(store: IncidentStore) -> None:
    for index in range(3):
        store.add(make_incident(incident_id=f"inc-{index}", at=OPENED_AT + timedelta(hours=index)))

    first = store.list_incidents(limit=2, offset=0)
    second = store.list_incidents(limit=2, offset=2)

    assert [incident.id for incident in first] == ["inc-2", "inc-1"]
    assert [incident.id for incident in second] == ["inc-0"]


def test_count_reports_matches(store: IncidentStore) -> None:
    store.add(make_incident(incident_id="inc-open"))
    resolved = make_incident(incident_id="inc-resolved").transition_to(
        IncidentStatus.RESOLVED, at=OPENED_AT + timedelta(hours=1)
    )
    store.add(resolved)

    assert store.count() == 2
    assert store.count(status=IncidentStatus.RESOLVED) == 1
    assert store.count(status=IncidentStatus.CLOSED) == 0


def test_list_rejects_invalid_pagination(store: IncidentStore) -> None:
    with pytest.raises(ValueError):
        store.list_incidents(limit=0)
    with pytest.raises(ValueError):
        store.list_incidents(offset=-1)
