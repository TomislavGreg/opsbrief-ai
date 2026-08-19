"""Tests for holding event fields back from AI context material."""

import pytest

from opsbrief.exclusion import (
    EXCLUDABLE_CONTEXT_FIELDS,
    EXCLUSION_PLACEHOLDER,
    normalise_excluded_fields,
    shown_value,
)


def test_normalise_keeps_known_fields() -> None:
    assert normalise_excluded_fields(["subject", "source"]) == {"subject", "source"}


def test_normalise_lowercases_and_strips() -> None:
    assert normalise_excluded_fields([" Subject ", "EVENT_TYPE"]) == {"subject", "event_type"}


def test_normalise_drops_blanks() -> None:
    assert normalise_excluded_fields(["subject", "", "  "]) == {"subject"}


def test_normalise_returns_empty_for_no_fields() -> None:
    assert normalise_excluded_fields([""]) == frozenset()


def test_normalise_rejects_an_unknown_field() -> None:
    """A field that is not renderable must fail loudly rather than be ignored."""
    with pytest.raises(ValueError, match="unknown AI context field 'entity_id'"):
        normalise_excluded_fields(["entity_id"])


def test_excludable_fields_cover_the_rendered_event_line() -> None:
    expected = {"source", "event_type", "subject", "severity", "status", "occurred_at"}
    assert expected == EXCLUDABLE_CONTEXT_FIELDS


def test_shown_value_masks_an_excluded_field() -> None:
    assert shown_value("subject", "Steward shift is short", {"subject"}) == EXCLUSION_PLACEHOLDER


def test_shown_value_keeps_an_included_field() -> None:
    assert shown_value("source", "rostering", {"subject"}) == "rostering"


def test_shown_value_keeps_everything_when_nothing_is_excluded() -> None:
    assert shown_value("subject", "Steward shift is short", frozenset()) == "Steward shift is short"
