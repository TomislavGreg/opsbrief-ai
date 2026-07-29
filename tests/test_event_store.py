"""Tests for SQLite event persistence."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from opsbrief.events import Event, EventInput, EventSeverity, EventStatus
from opsbrief.storage import DuplicateEventIdError, EventStore, database_path

OCCURRED_AT = datetime(2026, 7, 29, 9, 30, tzinfo=UTC)


@pytest.fixture
def store() -> Iterator[EventStore]:
    """Return a store backed by a throwaway in-memory database."""
    with EventStore.open("sqlite:///:memory:") as store:
        yield store


def make_event(*, received_at: datetime | None = None, **overrides: object) -> Event:
    """Return a stored event built from a valid submission."""
    payload: dict[str, object] = {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is unfilled",
        "occurred_at": OCCURRED_AT,
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload), received_at=received_at)


def test_stored_event_is_returned_unchanged(store: EventStore) -> None:
    event = make_event(
        severity="high",
        status="blocked",
        entity_type="fixture",
        entity_id="4821",
        due_at=datetime(2026, 7, 29, 18, 0, tzinfo=UTC),
        external_id="roster-9912",
        metadata={"venue": "North Stand", "required": 4, "fill_rate": 0.75, "urgent": True},
    )

    store.add(event)

    assert store.get(event.id) == event


def test_minimal_event_round_trips(store: EventStore) -> None:
    event = make_event()

    store.add(event)
    stored = store.get(event.id)

    assert stored is not None
    assert stored.severity is EventSeverity.INFO
    assert stored.status is None
    assert stored.due_at is None
    assert stored.external_id is None
    assert stored.metadata == {}


def test_stored_status_and_metadata_keep_their_types(store: EventStore) -> None:
    event = make_event(
        status="overdue",
        metadata={"required": 4, "fill_rate": 0.75, "urgent": True, "note": None},
    )

    store.add(event)
    stored = store.get(event.id)

    assert stored is not None
    assert stored.status is EventStatus.OVERDUE
    assert stored.metadata == {"required": 4, "fill_rate": 0.75, "urgent": True, "note": None}


def test_timestamps_come_back_in_utc(store: EventStore) -> None:
    local = timezone(timedelta(hours=2))
    event = make_event(
        occurred_at=datetime(2026, 7, 29, 11, 30, tzinfo=local),
        due_at=datetime(2026, 7, 29, 20, 0, tzinfo=local),
    )

    store.add(event)
    stored = store.get(event.id)

    assert stored is not None
    assert stored.occurred_at == OCCURRED_AT
    assert stored.occurred_at.tzinfo is UTC
    assert stored.due_at == datetime(2026, 7, 29, 18, 0, tzinfo=UTC)
    assert stored.received_at.tzinfo is UTC


def test_sub_second_precision_survives_storage(store: EventStore) -> None:
    event = make_event(occurred_at=datetime(2026, 7, 29, 9, 30, 15, 123456, tzinfo=UTC))

    store.add(event)
    stored = store.get(event.id)

    assert stored is not None
    assert stored.occurred_at == datetime(2026, 7, 29, 9, 30, 15, 123456, tzinfo=UTC)


def test_get_returns_none_for_an_unknown_id(store: EventStore) -> None:
    assert store.get("does-not-exist") is None


def test_add_rejects_a_repeated_id(store: EventStore) -> None:
    event = make_event()
    store.add(event)

    with pytest.raises(DuplicateEventIdError):
        store.add(event)

    assert store.count() == 1


def test_events_are_listed_most_recently_occurred_first(store: EventStore) -> None:
    older = make_event(occurred_at=OCCURRED_AT - timedelta(hours=2))
    newer = make_event(occurred_at=OCCURRED_AT + timedelta(hours=2))
    store.add(older)
    store.add(make_event())
    store.add(newer)

    listed = store.list_events()

    assert [event.occurred_at for event in listed] == [
        newer.occurred_at,
        OCCURRED_AT,
        older.occurred_at,
    ]


def test_listing_respects_the_limit(store: EventStore) -> None:
    for hour in range(5):
        store.add(make_event(occurred_at=OCCURRED_AT + timedelta(hours=hour)))

    listed = store.list_events(limit=2)

    assert len(listed) == 2
    assert listed[0].occurred_at == OCCURRED_AT + timedelta(hours=4)


def test_listing_ties_are_ordered_consistently(store: EventStore) -> None:
    received_at = datetime(2026, 7, 29, 9, 31, tzinfo=UTC)
    for _ in range(5):
        store.add(make_event(received_at=received_at))

    first = [event.id for event in store.list_events()]
    second = [event.id for event in store.list_events()]

    assert first == second


def test_listing_rejects_a_limit_below_one(store: EventStore) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        store.list_events(limit=0)


def test_an_empty_store_lists_nothing(store: EventStore) -> None:
    assert store.list_events() == []
    assert store.count() == 0


def test_events_survive_reopening_a_file_database(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'opsbrief.db'}"
    event = make_event()

    with EventStore.open(database_url) as store:
        store.add(event)

    with EventStore.open(database_url) as reopened:
        assert reopened.get(event.id) == event
        assert reopened.count() == 1


def test_opening_creates_a_missing_directory(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'data' / 'opsbrief.db'}"

    with EventStore.open(database_url) as store:
        store.add(make_event())

    assert (tmp_path / "data" / "opsbrief.db").exists()


def test_database_path_reads_a_sqlite_url() -> None:
    assert database_path("sqlite:///./opsbrief.db") == "./opsbrief.db"
    assert database_path("sqlite:////var/lib/opsbrief.db") == "/var/lib/opsbrief.db"
    assert database_path("sqlite:///:memory:") == ":memory:"


@pytest.mark.parametrize(
    "database_url",
    ["postgresql://localhost/opsbrief", "opsbrief.db", "sqlite://", "sqlite:///  "],
)
def test_unsupported_database_urls_are_rejected(database_url: str) -> None:
    with pytest.raises(ValueError):
        database_path(database_url)
