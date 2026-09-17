"""Tests for verifying an incident's new evidence against stored events."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from opsbrief.events import Event, EventInput
from opsbrief.services import UnknownEventIdsError, verify_events_exist
from opsbrief.storage import EventStore

OCCURRED_AT = datetime(2026, 8, 16, 9, 30, tzinfo=UTC)


@pytest.fixture
def store() -> Iterator[EventStore]:
    """Return an event store backed by a throwaway in-memory database."""
    with EventStore.open("sqlite:///:memory:") as store:
        yield store


def add_event(store: EventStore) -> str:
    """Store one event and return its assigned id."""
    event = Event.from_input(
        EventInput(
            source="integrations",
            event_type="integration.failed",
            subject="Ticketing webhook failed",
            occurred_at=OCCURRED_AT,
        )
    )
    store.add(event)
    return event.id


def test_all_known_ids_pass(store: EventStore) -> None:
    first = add_event(store)
    second = add_event(store)

    verify_events_exist(store, [first, second])


def test_an_empty_list_passes(store: EventStore) -> None:
    verify_events_exist(store, [])


def test_an_unknown_id_is_rejected(store: EventStore) -> None:
    known = add_event(store)

    with pytest.raises(UnknownEventIdsError) as error:
        verify_events_exist(store, [known, "not-a-stored-event"])

    assert error.value.event_ids == ["not-a-stored-event"]
    assert "not-a-stored-event" in str(error.value)


def test_all_unknown_ids_are_named(store: EventStore) -> None:
    with pytest.raises(UnknownEventIdsError) as error:
        verify_events_exist(store, ["gone-1", "gone-2"])

    assert error.value.event_ids == ["gone-1", "gone-2"]
