"""Tests for the incident-summary contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opsbrief.incidents import (
    INCIDENT_SUMMARY_OUTPUT_VERSION,
    INCIDENT_SUMMARY_PROMPT_VERSION,
    MAX_INCIDENT_SUMMARY_LENGTH,
    Confidence,
    GenerationWarning,
    IncidentSeverity,
    IncidentStatus,
    IncidentSummary,
    WarningCode,
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)


def make_summary(**overrides: object) -> IncidentSummary:
    """Build a valid incident summary, overriding fields for a given test."""
    payload: dict[str, object] = {
        "incident_id": "inc-1",
        "title": "Ticketing integration failing repeatedly",
        "status": IncidentStatus.INVESTIGATING,
        "severity": IncidentSeverity.HIGH,
        "summary": "The ticketing webhook failed repeatedly and is being investigated.",
        "model": "fake-1",
        "source_event_ids": ["e17", "e18"],
    }
    payload.update(overrides)
    return IncidentSummary(**payload)


def test_versions_default_to_the_current_values() -> None:
    summary = make_summary()

    assert summary.output_version == INCIDENT_SUMMARY_OUTPUT_VERSION
    assert summary.prompt_version == INCIDENT_SUMMARY_PROMPT_VERSION


def test_missing_and_notes_default_to_empty() -> None:
    summary = make_summary()

    assert summary.missing_event_ids == []
    assert summary.notes == []
    assert summary.started_at is None
    assert summary.ended_at is None


def test_a_summary_carries_its_incident_details_and_evidence() -> None:
    summary = make_summary(
        started_at=NOW,
        ended_at=NOW,
        missing_event_ids=["e19"],
        notes=["One cited event no longer resolves."],
    )

    assert summary.incident_id == "inc-1"
    assert summary.status is IncidentStatus.INVESTIGATING
    assert summary.severity is IncidentSeverity.HIGH
    assert summary.source_event_ids == ["e17", "e18"]
    assert summary.missing_event_ids == ["e19"]


def test_confidence_is_derived_from_the_warnings() -> None:
    # No warnings reads as full confidence; a missing-evidence warning lowers it,
    # and the two never disagree because confidence is computed from the warnings.
    assert make_summary().confidence is Confidence.HIGH

    degraded = make_summary(
        warnings=[GenerationWarning(code=WarningCode.MISSING_EVENTS, message="1 cited event gone.")]
    )
    assert degraded.confidence is Confidence.LOW
    assert degraded.model_dump()["confidence"] == "low"


def test_an_empty_summary_is_allowed() -> None:
    summary = make_summary(summary="")

    assert summary.summary == ""


def test_a_summary_longer_than_the_bound_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_summary(summary="x" * (MAX_INCIDENT_SUMMARY_LENGTH + 1))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        make_summary(unexpected="value")


def test_the_model_is_required() -> None:
    with pytest.raises(ValidationError):
        make_summary(model="")
