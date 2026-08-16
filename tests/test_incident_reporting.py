"""Tests for the incident declaration and retrieval services."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from opsbrief.incidents import (
    IncidentDeclaration,
    IncidentQuery,
    IncidentSeverity,
    IncidentStatus,
)
from opsbrief.services import declare_incident, get_incident, list_incidents
from opsbrief.storage import DuplicateIncidentIdError, IncidentStore

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def store() -> Iterator[IncidentStore]:
    """Return a store backed by a throwaway in-memory database."""
    with IncidentStore.open("sqlite:///:memory:") as store:
        yield store


def make_declaration(
    *,
    title: str = "Ticketing integration failing repeatedly",
    severity: IncidentSeverity = IncidentSeverity.HIGH,
    event_ids: list[str] | None = None,
) -> IncidentDeclaration:
    """Return a declaration request body."""
    return IncidentDeclaration(
        title=title,
        severity=severity,
        event_ids=event_ids or ["e17", "e18"],
    )


def test_declaring_stores_an_open_incident(store: IncidentStore) -> None:
    incident = declare_incident(store, make_declaration(), NOW)

    assert incident.status is IncidentStatus.OPEN
    assert incident.title == "Ticketing integration failing repeatedly"
    assert incident.severity is IncidentSeverity.HIGH
    assert incident.event_ids == ["e17", "e18"]
    assert incident.opened_at == NOW
    assert incident.updated_at == NOW
    assert incident.resolved_at is None


def test_a_declared_incident_can_be_read_back(store: IncidentStore) -> None:
    declared = declare_incident(store, make_declaration(), NOW)

    fetched = get_incident(store, declared.id)

    assert fetched is not None
    assert fetched.id == declared.id
    assert fetched.event_ids == ["e17", "e18"]


def test_each_declaration_gets_a_distinct_identifier(store: IncidentStore) -> None:
    first = declare_incident(store, make_declaration(), NOW)
    second = declare_incident(store, make_declaration(), NOW)

    assert first.id != second.id
    assert store.count() == 2


def test_getting_an_unknown_incident_returns_none(store: IncidentStore) -> None:
    assert get_incident(store, "missing") is None


def test_listing_reports_the_total_and_the_page(store: IncidentStore) -> None:
    declare_incident(store, make_declaration(title="First"), NOW)
    declare_incident(store, make_declaration(title="Second"), NOW)

    page = list_incidents(store, IncidentQuery(limit=1))

    assert page.total == 2
    assert page.limit == 1
    assert page.offset == 0
    assert len(page.incidents) == 1


def test_listing_filters_by_status(store: IncidentStore) -> None:
    open_incident = declare_incident(store, make_declaration(title="Open one"), NOW)
    declare_incident(store, make_declaration(title="Another open"), NOW)
    store.save(open_incident.transition_to(IncidentStatus.INVESTIGATING, at=NOW))

    investigating = list_incidents(store, IncidentQuery(status=IncidentStatus.INVESTIGATING))
    still_open = list_incidents(store, IncidentQuery(status=IncidentStatus.OPEN))

    assert investigating.total == 1
    assert investigating.incidents[0].title == "Open one"
    assert still_open.total == 1
    assert still_open.incidents[0].title == "Another open"


def test_listing_an_empty_store_is_an_empty_page(store: IncidentStore) -> None:
    page = list_incidents(store, IncidentQuery())

    assert page.total == 0
    assert page.incidents == []


def test_a_duplicate_identifier_surfaces_from_the_store(store: IncidentStore) -> None:
    # Two declarations with the same generated id would clash; force the case by
    # re-adding the stored incident under its own id.
    incident = declare_incident(store, make_declaration(), NOW)

    with pytest.raises(DuplicateIncidentIdError):
        store.add(incident)
