"""Tests for the operational event schema."""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from opsbrief.events import (
    DEFAULT_PAGE_SIZE,
    MAX_METADATA_ENTRIES,
    MAX_METADATA_VALUE_LENGTH,
    MAX_PAGE_SIZE,
    Event,
    EventInput,
    EventQuery,
    EventSeverity,
    EventStatus,
)

OCCURRED_AT = datetime(2026, 7, 29, 9, 30, tzinfo=UTC)


def make_payload(**overrides: object) -> dict[str, object]:
    """Return a valid submission payload with the given fields replaced."""
    payload: dict[str, object] = {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is unfilled",
        "occurred_at": OCCURRED_AT,
    }
    payload.update(overrides)
    return payload


def test_minimal_payload_is_accepted() -> None:
    event = EventInput(**make_payload())

    assert event.source == "rostering"
    assert event.event_type == "shift.unfilled"
    assert event.occurred_at == OCCURRED_AT


def test_optional_fields_default_to_neutral_values() -> None:
    event = EventInput(**make_payload())

    assert event.severity is EventSeverity.INFO
    assert event.status is None
    assert event.entity_type is None
    assert event.entity_id is None
    assert event.due_at is None
    assert event.external_id is None
    assert event.metadata == {}


def test_full_payload_round_trips_through_json() -> None:
    event = EventInput(
        **make_payload(
            severity="high",
            status="blocked",
            entity_type="fixture",
            entity_id="4821",
            due_at=datetime(2026, 7, 29, 18, 0, tzinfo=UTC),
            external_id="roster-9912",
            metadata={"venue": "North Stand", "required": 4, "assigned": 3, "urgent": True},
        )
    )

    restored = EventInput.model_validate_json(event.model_dump_json())

    assert restored == event
    assert restored.severity is EventSeverity.HIGH
    assert restored.status is EventStatus.BLOCKED


def test_whitespace_is_stripped_from_text_fields() -> None:
    event = EventInput(**make_payload(subject="  Steward shift is unfilled  "))

    assert event.subject == "Steward shift is unfilled"


def test_blank_subject_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventInput(**make_payload(subject="   "))


@pytest.mark.parametrize(
    "event_type",
    ["Shift.Unfilled", "shift unfilled", "shift..unfilled", ".shift", "no", "shift/unfilled"],
)
def test_malformed_event_type_is_rejected(event_type: str) -> None:
    with pytest.raises(ValidationError):
        EventInput(**make_payload(event_type=event_type))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        EventInput(**make_payload(priority="urgent"))


def test_naive_occurred_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        EventInput(**make_payload(occurred_at=datetime(2026, 7, 29, 9, 30)))


def test_naive_due_at_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        EventInput(**make_payload(due_at=datetime(2026, 7, 29, 18, 0)))


def test_timestamps_are_normalised_to_utc() -> None:
    local = timezone(timedelta(hours=2))
    event = EventInput(
        **make_payload(
            occurred_at=datetime(2026, 7, 29, 11, 30, tzinfo=local),
            due_at=datetime(2026, 7, 29, 20, 0, tzinfo=local),
        )
    )

    assert event.occurred_at == OCCURRED_AT
    assert event.occurred_at.tzinfo is UTC
    assert event.due_at == datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def test_due_at_may_precede_occurred_at() -> None:
    event = EventInput(
        **make_payload(
            event_type="task.overdue",
            due_at=datetime(2026, 7, 28, 18, 0, tzinfo=UTC),
        )
    )

    assert event.due_at is not None
    assert event.due_at < event.occurred_at


def test_entity_type_without_entity_id_is_rejected() -> None:
    with pytest.raises(ValidationError, match="together"):
        EventInput(**make_payload(entity_type="fixture"))


def test_entity_id_without_entity_type_is_rejected() -> None:
    with pytest.raises(ValidationError, match="together"):
        EventInput(**make_payload(entity_id="4821"))


def test_nested_metadata_is_rejected() -> None:
    with pytest.raises(ValidationError):
        EventInput(**make_payload(metadata={"roster": {"required": 4}}))


def test_metadata_entry_limit_is_enforced() -> None:
    too_many = {f"key_{index}": index for index in range(MAX_METADATA_ENTRIES + 1)}

    with pytest.raises(ValidationError, match="at most"):
        EventInput(**make_payload(metadata=too_many))


def test_oversized_metadata_value_is_rejected() -> None:
    oversized = {"note": "x" * (MAX_METADATA_VALUE_LENGTH + 1)}

    with pytest.raises(ValidationError, match="exceeds"):
        EventInput(**make_payload(metadata=oversized))


def test_metadata_accepts_scalar_values_including_none() -> None:
    event = EventInput(
        **make_payload(metadata={"required": 4, "fill_rate": 0.75, "urgent": True, "note": None})
    )

    assert event.metadata == {"required": 4, "fill_rate": 0.75, "urgent": True, "note": None}


def test_from_input_assigns_identity_and_keeps_submitted_fields() -> None:
    payload = EventInput(**make_payload(status="blocked", metadata={"required": 4}))
    received_at = datetime(2026, 7, 29, 9, 31, tzinfo=UTC)

    event = Event.from_input(payload, received_at=received_at)

    assert event.id
    assert event.received_at == received_at
    assert event.subject == payload.subject
    assert event.status is EventStatus.BLOCKED
    assert event.metadata == {"required": 4}


def test_from_input_assigns_a_distinct_id_per_event() -> None:
    payload = EventInput(**make_payload())

    first = Event.from_input(payload)
    second = Event.from_input(payload)

    assert first.id != second.id


def test_from_input_defaults_received_at_to_now_in_utc() -> None:
    before = datetime.now(UTC)

    event = Event.from_input(EventInput(**make_payload()))

    assert event.received_at.tzinfo is UTC
    assert before <= event.received_at <= datetime.now(UTC)


def test_stored_event_rejects_a_naive_received_at() -> None:
    with pytest.raises(ValidationError, match="timezone offset"):
        Event(**make_payload(), id="abc123", received_at=datetime(2026, 7, 29, 9, 31))


def test_event_query_defaults_to_an_unfiltered_first_page() -> None:
    query = EventQuery()

    assert query.source is None
    assert query.event_type is None
    assert query.severity is None
    assert query.status is None
    assert query.limit == DEFAULT_PAGE_SIZE
    assert query.offset == 0


def test_event_query_parses_filters_and_pagination() -> None:
    query = EventQuery(
        source="integrations", severity="high", status="blocked", limit=10, offset=20
    )

    assert query.source == "integrations"
    assert query.severity is EventSeverity.HIGH
    assert query.status is EventStatus.BLOCKED
    assert query.limit == 10
    assert query.offset == 20


@pytest.mark.parametrize(
    "overrides",
    [
        {"limit": 0},
        {"limit": MAX_PAGE_SIZE + 1},
        {"offset": -1},
        {"severity": "catastrophic"},
        {"status": "pending"},
        {"source": ""},
        {"unknown": "value"},
    ],
)
def test_event_query_rejects_invalid_input(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EventQuery(**overrides)
