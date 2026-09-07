"""Tests for holding event fields back from AI context material."""

import pytest

from opsbrief.exclusion import (
    EXCLUDABLE_CONTEXT_FIELDS,
    EXCLUSION_PLACEHOLDER,
    INCIDENT_FREE_TEXT_CONTROL,
    normalise_excluded_fields,
    shown_free_text,
    shown_incident_title,
    shown_risk_title,
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


def test_normalise_accepts_the_free_text_control() -> None:
    assert normalise_excluded_fields([INCIDENT_FREE_TEXT_CONTROL]) == {INCIDENT_FREE_TEXT_CONTROL}


def test_risk_title_is_held_back_when_subject_is_excluded() -> None:
    assert shown_risk_title("Inspection is overdue", {"subject"}) == EXCLUSION_PLACEHOLDER


def test_risk_title_is_shown_when_subject_is_included() -> None:
    assert shown_risk_title("Inspection is overdue", {"status"}) == "Inspection is overdue"


def test_incident_title_is_held_back_when_subject_is_excluded() -> None:
    assert shown_incident_title("Ticketing failing", {"subject"}) == EXCLUSION_PLACEHOLDER


def test_incident_title_is_held_back_under_the_free_text_control() -> None:
    assert (
        shown_incident_title("Ticketing failing", {INCIDENT_FREE_TEXT_CONTROL})
        == EXCLUSION_PLACEHOLDER
    )


def test_incident_title_is_shown_by_default() -> None:
    assert shown_incident_title("Ticketing failing", frozenset()) == "Ticketing failing"


def test_resolution_note_is_held_back_only_under_the_free_text_control() -> None:
    assert (
        shown_free_text("Restarted the sync", {INCIDENT_FREE_TEXT_CONTROL}) == EXCLUSION_PLACEHOLDER
    )
    # A field exclusion does not reach operator free text.
    assert shown_free_text("Restarted the sync", {"subject"}) == "Restarted the sync"
