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


def test_add_or_get_stores_a_new_event(store: EventStore) -> None:
    event = make_event(external_id="roster-9912")

    stored = store.add_or_get(event)

    assert stored == event
    assert store.get(event.id) == event
    assert store.count() == 1


def test_add_or_get_recognises_a_resubmission(store: EventStore) -> None:
    first = make_event(external_id="roster-9912")
    store.add_or_get(first)

    resubmission = make_event(external_id="roster-9912", subject="Same event, sent again")
    returned = store.add_or_get(resubmission)

    assert returned.id == first.id
    assert returned.subject == first.subject
    assert store.count() == 1


def test_add_or_get_scopes_the_key_to_the_source(store: EventStore) -> None:
    store.add_or_get(make_event(source="rostering", external_id="shared-1"))
    stored = store.add_or_get(make_event(source="integrations", external_id="shared-1"))

    assert store.get(stored.id) is not None
    assert store.count() == 2


def test_add_or_get_never_deduplicates_without_an_external_id(store: EventStore) -> None:
    first = store.add_or_get(make_event())
    second = store.add_or_get(make_event())

    assert first.id != second.id
    assert store.count() == 2


def test_add_or_get_treats_a_blank_external_id_as_no_key(store: EventStore) -> None:
    first = store.add_or_get(make_event(external_id=""))
    second = store.add_or_get(make_event(external_id=""))

    assert first.id != second.id
    assert store.count() == 2


def test_add_or_get_still_rejects_a_repeated_id(store: EventStore) -> None:
    event = make_event()
    store.add(event)

    with pytest.raises(DuplicateEventIdError):
        store.add_or_get(event)

    assert store.count() == 1


def test_add_all_stores_every_event(store: EventStore) -> None:
    events = [make_event(subject=f"Event {index}") for index in range(3)]

    returned = store.add_all(events)

    assert returned == events
    assert store.count() == 3
    for event in events:
        assert store.get(event.id) == event


def test_add_all_stores_nothing_for_an_empty_batch(store: EventStore) -> None:
    assert store.add_all([]) == []
    assert store.count() == 0


def test_add_all_is_all_or_nothing_on_a_repeated_id(store: EventStore) -> None:
    duplicate = make_event()

    with pytest.raises(DuplicateEventIdError):
        store.add_all([make_event(), duplicate, duplicate])

    assert store.count() == 0


def test_add_all_rejects_ids_already_stored(store: EventStore) -> None:
    existing = make_event()
    store.add(existing)

    with pytest.raises(DuplicateEventIdError):
        store.add_all([make_event(), existing])

    assert store.count() == 1


def test_add_all_or_get_stores_a_batch_of_new_events(store: EventStore) -> None:
    events = [make_event(subject=f"Event {index}") for index in range(3)]

    returned = store.add_all_or_get(events)

    assert returned == events
    assert store.count() == 3


def test_add_all_or_get_stores_nothing_for_an_empty_batch(store: EventStore) -> None:
    assert store.add_all_or_get([]) == []
    assert store.count() == 0


def test_add_all_or_get_recognises_events_already_stored(store: EventStore) -> None:
    first = make_event(external_id="roster-9912")
    store.add_or_get(first)

    resubmission = make_event(external_id="roster-9912", subject="Sent again in a batch")
    fresh = make_event(external_id="roster-1001")
    returned = store.add_all_or_get([resubmission, fresh])

    assert returned[0].id == first.id
    assert returned[0].subject == first.subject
    assert returned[1].id == fresh.id
    assert store.count() == 2


def test_add_all_or_get_deduplicates_within_the_batch(store: EventStore) -> None:
    first = make_event(external_id="roster-9912", subject="First wording")
    duplicate = make_event(external_id="roster-9912", subject="Reworded in the same batch")

    returned = store.add_all_or_get([first, duplicate])

    assert returned[0].id == first.id
    assert returned[1].id == first.id
    assert returned[1].subject == "First wording"
    assert store.count() == 1


def test_add_all_or_get_scopes_the_key_to_the_source(store: EventStore) -> None:
    returned = store.add_all_or_get(
        [
            make_event(source="rostering", external_id="shared-1"),
            make_event(source="integrations", external_id="shared-1"),
        ]
    )

    assert returned[0].id != returned[1].id
    assert store.count() == 2


def test_add_all_or_get_never_deduplicates_without_an_external_id(store: EventStore) -> None:
    returned = store.add_all_or_get([make_event(), make_event()])

    assert returned[0].id != returned[1].id
    assert store.count() == 2


def test_add_all_or_get_is_all_or_nothing_on_a_repeated_id(store: EventStore) -> None:
    duplicate = make_event()

    with pytest.raises(DuplicateEventIdError):
        store.add_all_or_get([make_event(), duplicate, duplicate])

    assert store.count() == 0


def test_add_all_or_get_keeps_a_stored_resubmission_when_a_later_id_clashes(
    store: EventStore,
) -> None:
    existing = make_event(external_id="roster-9912")
    store.add_or_get(existing)
    clash = make_event()
    store.add(clash)

    with pytest.raises(DuplicateEventIdError):
        store.add_all_or_get([make_event(external_id="roster-9912"), clash])

    assert store.count() == 2


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


def test_listing_pages_through_events_with_an_offset(store: EventStore) -> None:
    for hour in range(5):
        store.add(make_event(occurred_at=OCCURRED_AT + timedelta(hours=hour)))

    first_page = store.list_events(limit=2, offset=0)
    second_page = store.list_events(limit=2, offset=2)
    third_page = store.list_events(limit=2, offset=4)

    occurred = [
        event.occurred_at for page in (first_page, second_page, third_page) for event in page
    ]
    assert occurred == [OCCURRED_AT + timedelta(hours=hour) for hour in (4, 3, 2, 1, 0)]
    assert len(third_page) == 1


def test_offset_past_the_end_returns_nothing(store: EventStore) -> None:
    store.add(make_event())

    assert store.list_events(offset=5) == []


def test_listing_filters_by_source(store: EventStore) -> None:
    store.add(make_event(source="rostering"))
    store.add(make_event(source="integrations"))

    listed = store.list_events(source="integrations")

    assert [event.source for event in listed] == ["integrations"]


def test_listing_filters_by_severity_and_status(store: EventStore) -> None:
    store.add(make_event(severity="high", status="blocked"))
    store.add(make_event(severity="high", status="open"))
    store.add(make_event(severity="low", status="blocked"))

    listed = store.list_events(severity=EventSeverity.HIGH, status=EventStatus.BLOCKED)

    assert len(listed) == 1
    assert listed[0].severity is EventSeverity.HIGH
    assert listed[0].status is EventStatus.BLOCKED


def test_listing_filters_combine_and_page_together(store: EventStore) -> None:
    for hour in range(4):
        store.add(
            make_event(source="integrations", occurred_at=OCCURRED_AT + timedelta(hours=hour))
        )
    store.add(make_event(source="rostering"))

    page = store.list_events(source="integrations", limit=2, offset=1)

    assert [event.occurred_at for event in page] == [
        OCCURRED_AT + timedelta(hours=2),
        OCCURRED_AT + timedelta(hours=1),
    ]


def test_count_respects_filters(store: EventStore) -> None:
    store.add(make_event(source="integrations", severity="high"))
    store.add(make_event(source="integrations", severity="low"))
    store.add(make_event(source="rostering", severity="high"))

    assert store.count() == 3
    assert store.count(source="integrations") == 2
    assert store.count(severity=EventSeverity.HIGH) == 2
    assert store.count(source="integrations", severity=EventSeverity.HIGH) == 1


def test_listing_rejects_a_limit_below_one(store: EventStore) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        store.list_events(limit=0)


def test_listing_rejects_a_negative_offset(store: EventStore) -> None:
    with pytest.raises(ValueError, match="negative"):
        store.list_events(offset=-1)


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
