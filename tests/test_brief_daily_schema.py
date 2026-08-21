"""Tests for the daily-brief output contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opsbrief.brief import BRIEF_OUTPUT_VERSION, MAX_SUMMARY_LENGTH, DailyBrief
from opsbrief.risks import Risk, RiskSeverity
from opsbrief.warnings import Confidence, GenerationWarning, WarningCode

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def make_risk() -> Risk:
    return Risk(
        rule="overdue_work",
        title="Safety inspection is overdue",
        detail="Work was due earlier and is not resolved.",
        severity=RiskSeverity.HIGH,
        event_ids=["e04"],
    )


def test_daily_brief_carries_summary_and_structured_facts() -> None:
    brief = DailyBrief(
        generated_at=NOW,
        summary="One safety inspection is overdue; act on it first.",
        model="fake",
        risks=[make_risk()],
        notes=["Showing the 5 most recent of 12 events."],
        source_event_ids=["e04"],
    )

    assert brief.model == "fake"
    assert brief.risks[0].rule == "overdue_work"
    assert brief.source_event_ids == ["e04"]


def test_confidence_is_derived_from_the_warnings() -> None:
    # No warnings reads as full confidence; a warning lowers it, and the two never
    # disagree because confidence is computed from the warnings rather than stored.
    clear = DailyBrief(generated_at=NOW, summary="ok", model="fake", risks=[])
    assert clear.confidence is Confidence.HIGH

    partial = DailyBrief(
        generated_at=NOW,
        summary="",
        model="fake",
        risks=[],
        warnings=[GenerationWarning(code=WarningCode.MODEL_UNAVAILABLE, message="down")],
    )
    assert partial.confidence is Confidence.MEDIUM
    # The computed level is serialised alongside the stored fields.
    assert partial.model_dump()["confidence"] == "medium"


def test_summary_may_be_empty() -> None:
    brief = DailyBrief(generated_at=NOW, summary="", model="fake", risks=[])

    assert brief.summary == ""
    assert brief.notes == []
    assert brief.source_event_ids == []


def test_summary_is_length_bounded() -> None:
    with pytest.raises(ValidationError):
        DailyBrief(
            generated_at=NOW,
            summary="x" * (MAX_SUMMARY_LENGTH + 1),
            model="fake",
            risks=[],
        )


def test_model_is_required_for_traceability() -> None:
    with pytest.raises(ValidationError):
        DailyBrief(generated_at=NOW, summary="ok", model="", risks=[])


def test_output_version_defaults_to_the_current_structure_version() -> None:
    brief = DailyBrief(generated_at=NOW, summary="ok", model="fake", risks=[])

    assert brief.output_version == BRIEF_OUTPUT_VERSION
    assert brief.output_version


def test_output_version_may_be_overridden_but_not_left_blank() -> None:
    brief = DailyBrief(
        generated_at=NOW, summary="ok", model="fake", risks=[], output_version="daily-brief/2"
    )
    assert brief.output_version == "daily-brief/2"

    with pytest.raises(ValidationError):
        DailyBrief(generated_at=NOW, summary="ok", model="fake", risks=[], output_version="")


def test_daily_brief_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DailyBrief(
            generated_at=NOW,
            summary="ok",
            model="fake",
            risks=[],
            recommendations=["invent something"],
        )
