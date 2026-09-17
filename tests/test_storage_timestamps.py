"""Tests for the canonical fixed-width UTC timestamp representation.

The stored representation must be fixed-width across the whole supported year
range (1 through 9999) so that string order is chronological order, and it must
round-trip through the database for events and incidents. A year below 1000 once
serialised with an unpadded ``strftime`` that the parser could not read back,
which these tests pin against.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest

from opsbrief.events import Event, EventInput
from opsbrief.incidents import Incident, IncidentSeverity
from opsbrief.storage import EventStore, IncidentStore
from opsbrief.storage.event_store import format_timestamp, parse_timestamp

EXTREME_YEARS = [1, 42, 999, 1000, 2026, 9999]


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


@pytest.mark.parametrize("year", EXTREME_YEARS)
def test_year_is_zero_padded_to_four_digits(year: int) -> None:
    text = format_timestamp(datetime(year, 1, 1, tzinfo=UTC))

    assert text.startswith(f"{year:04d}-")
    assert len(text.split("-", 1)[0]) == 4


@pytest.mark.parametrize("year", EXTREME_YEARS)
def test_format_and_parse_round_trip(year: int) -> None:
    moment = datetime(year, 3, 4, 5, 6, 7, 123456, tzinfo=UTC)

    assert parse_timestamp(format_timestamp(moment)) == moment


def test_non_utc_offset_is_converted_before_storage() -> None:
    local = datetime(2026, 7, 29, 11, 30, tzinfo=timezone(timedelta(hours=2)))

    text = format_timestamp(local)

    assert text == "2026-07-29T09:30:00.000000Z"
    assert parse_timestamp(text) == local.astimezone(UTC)


def test_string_order_matches_chronological_order() -> None:
    texts = [format_timestamp(datetime(year, 1, 1, tzinfo=UTC)) for year in EXTREME_YEARS]

    assert texts == sorted(texts)


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("1-01-01T00:00:00.000000Z", datetime(1, 1, 1, tzinfo=UTC)),
        ("42-03-04T05:06:07.123456Z", datetime(42, 3, 4, 5, 6, 7, 123456, tzinfo=UTC)),
        ("999-12-31T23:59:59.999999Z", datetime(999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)),
    ],
)
def test_a_legacy_unpadded_year_is_read_back(stored: str, expected: datetime) -> None:
    # A row written before the year was zero-padded still reads back, exactly, as
    # the year it names rather than failing.
    assert parse_timestamp(stored) == expected


def test_an_unparseable_timestamp_still_raises() -> None:
    with pytest.raises(ValueError):
        parse_timestamp("not-a-timestamp")


def make_event(occurred_at: datetime) -> Event:
    """Return a stored event occurring at ``occurred_at``."""
    return Event.from_input(
        EventInput(
            source="integrations",
            event_type="integration.failed",
            subject="Ticketing webhook failed",
            occurred_at=occurred_at,
            due_at=occurred_at + timedelta(hours=1),
        ),
        received_at=occurred_at,
    )


@pytest.mark.parametrize("year", [1, 9999])
def test_event_round_trips_through_sqlite(event_store: EventStore, year: int) -> None:
    event = make_event(datetime(year, 6, 15, 8, 30, 15, 654321, tzinfo=UTC))

    event_store.add(event)

    assert event_store.get(event.id) == event
    assert event_store.list_all_events() == [event]


@pytest.mark.parametrize("year", [1, 9999])
def test_incident_round_trips_through_sqlite(incident_store: IncidentStore, year: int) -> None:
    opened = datetime(year, 6, 15, 8, 30, 15, 654321, tzinfo=UTC)
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=["e17", "e18"],
        at=opened,
    )

    incident_store.add(incident)

    assert incident_store.get(incident.id) == incident
