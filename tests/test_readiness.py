"""Tests for the readiness assessment service."""

from collections.abc import Iterator

import pytest

from opsbrief.services import check_readiness
from opsbrief.storage import EventStore, IncidentStore


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


def test_open_stores_are_ready(event_store: EventStore, incident_store: IncidentStore) -> None:
    readiness = check_readiness(event_store, incident_store)

    assert readiness.ready is True
    assert [check.name for check in readiness.checks] == ["event_store", "incident_store"]
    assert all(check.ready for check in readiness.checks)
    assert all(check.detail is None for check in readiness.checks)


def test_a_failing_store_makes_the_service_not_ready(
    event_store: EventStore, incident_store: IncidentStore
) -> None:
    # A closed store can no longer answer a probe; readiness must report the gap
    # rather than raise, so an orchestrator sees a not-ready result.
    incident_store.close()

    readiness = check_readiness(event_store, incident_store)

    assert readiness.ready is False
    event_check, incident_check = readiness.checks
    assert event_check.ready is True
    assert incident_check.ready is False
    assert incident_check.detail


def test_a_probe_failure_is_captured_not_raised(
    event_store: EventStore, incident_store: IncidentStore
) -> None:
    # Even both stores failing yields a structured answer, never an exception.
    event_store.close()
    incident_store.close()

    readiness = check_readiness(event_store, incident_store)

    assert readiness.ready is False
    assert all(check.ready is False for check in readiness.checks)
    assert all(check.detail for check in readiness.checks)


def test_an_unreachable_store_reports_a_safe_category(
    event_store: EventStore, incident_store: IncidentStore
) -> None:
    # The detail is a fixed safe category, never the raw exception text, so a
    # database path or driver message cannot leak through a public probe.
    incident_store.close()

    readiness = check_readiness(event_store, incident_store)

    incident_check = next(c for c in readiness.checks if c.name == "incident_store")
    assert incident_check.detail == "storage is unavailable"


def test_a_missing_table_is_reported_as_a_schema_gap(
    event_store: EventStore, incident_store: IncidentStore
) -> None:
    # An uninitialised schema is distinguished from an unreachable store, so an
    # operator can tell them apart, still without leaking the raw error.
    event_store._connection.execute("DROP TABLE events")

    readiness = check_readiness(event_store, incident_store)

    assert readiness.ready is False
    event_check = next(c for c in readiness.checks if c.name == "event_store")
    assert event_check.detail == "storage schema is unavailable"
