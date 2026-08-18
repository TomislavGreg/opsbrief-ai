"""Tests for sensitive-metadata redaction."""

from datetime import UTC, datetime

from opsbrief.events import Event, EventInput
from opsbrief.redaction import (
    DEFAULT_SENSITIVE_KEYS,
    REDACTION_PLACEHOLDER,
    redact_event,
    redact_event_input,
    redact_metadata,
)


def test_masks_a_default_sensitive_key() -> None:
    redacted = redact_metadata({"email": "sam@example.com"})

    assert redacted == {"email": REDACTION_PLACEHOLDER}


def test_leaves_non_sensitive_values_untouched() -> None:
    redacted = redact_metadata({"required": 4, "assigned": 3, "venue": "North Stand"})

    assert redacted == {"required": 4, "assigned": 3, "venue": "North Stand"}


def test_matches_a_term_anywhere_in_the_key() -> None:
    redacted = redact_metadata({"customer_email": "sam@example.com", "phone_number": "555-0100"})

    assert redacted == {
        "customer_email": REDACTION_PLACEHOLDER,
        "phone_number": REDACTION_PLACEHOLDER,
    }


def test_matching_is_case_insensitive() -> None:
    redacted = redact_metadata({"Contact_Email": "sam@example.com"})

    assert redacted == {"Contact_Email": REDACTION_PLACEHOLDER}


def test_absent_value_is_left_as_none() -> None:
    """A null value carries nothing to hide, so it is not turned into a mask."""
    redacted = redact_metadata({"email": None})

    assert redacted == {"email": None}


def test_non_string_sensitive_value_is_masked() -> None:
    redacted = redact_metadata({"api_key": 12345})

    assert redacted == {"api_key": REDACTION_PLACEHOLDER}


def test_key_order_is_preserved() -> None:
    redacted = redact_metadata({"venue": "North Stand", "email": "sam@example.com", "seats": 200})

    assert list(redacted) == ["venue", "email", "seats"]


def test_empty_metadata_returns_empty() -> None:
    assert redact_metadata({}) == {}


def test_source_metadata_is_not_mutated() -> None:
    original = {"email": "sam@example.com"}
    redact_metadata(original)

    assert original == {"email": "sam@example.com"}


def test_custom_terms_replace_the_defaults() -> None:
    """Passing an explicit term set redacts exactly those keys, not the defaults."""
    redacted = redact_metadata({"email": "sam@example.com", "seat": "12A"}, sensitive_keys={"seat"})

    assert redacted == {"email": "sam@example.com", "seat": REDACTION_PLACEHOLDER}


def test_blank_terms_are_ignored() -> None:
    """A blank term must not match every key and blank out the whole metadata."""
    redacted = redact_metadata({"venue": "North Stand"}, sensitive_keys={"  ", ""})

    assert redacted == {"venue": "North Stand"}


def test_default_keys_cover_common_secrets() -> None:
    for term in ("password", "token", "secret", "ssn"):
        assert term in DEFAULT_SENSITIVE_KEYS


def _event_input(metadata: dict[str, object]) -> EventInput:
    return EventInput(
        source="rostering",
        event_type="shift.unfilled",
        subject="Steward shift is one short",
        occurred_at=datetime(2026, 7, 29, 9, 30, tzinfo=UTC),
        metadata=metadata,
    )


def test_redact_event_input_masks_metadata_only() -> None:
    payload = _event_input({"email": "sam@example.com", "required": 4})
    redacted = redact_event_input(payload)

    assert redacted.metadata == {"email": REDACTION_PLACEHOLDER, "required": 4}
    assert redacted.subject == payload.subject
    assert redacted.source == payload.source


def test_redact_event_input_returns_same_object_when_nothing_matches() -> None:
    payload = _event_input({"required": 4})

    assert redact_event_input(payload) is payload


def test_redact_event_input_does_not_mutate_the_payload() -> None:
    payload = _event_input({"email": "sam@example.com"})
    redact_event_input(payload)

    assert payload.metadata == {"email": "sam@example.com"}


def test_redact_event_masks_a_stored_event() -> None:
    event = Event.from_input(_event_input({"api_key": "abc123", "venue": "North Stand"}))
    redacted = redact_event(event)

    assert redacted.metadata == {"api_key": REDACTION_PLACEHOLDER, "venue": "North Stand"}
    assert redacted.id == event.id
    assert redacted.received_at == event.received_at
