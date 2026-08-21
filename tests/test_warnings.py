"""Tests for generation warnings and the confidence they imply."""

import pytest
from pydantic import ValidationError

from opsbrief.warnings import (
    Confidence,
    GenerationWarning,
    WarningCode,
    assess_confidence,
)


def warning(code: WarningCode) -> GenerationWarning:
    """Build a warning with the given code and a placeholder message."""
    return GenerationWarning(code=code, message=f"message for {code.value}")


def test_a_warning_pairs_a_code_with_a_message() -> None:
    result = GenerationWarning(code=WarningCode.MISSING_EVENTS, message="1 cited event is gone.")

    assert result.code is WarningCode.MISSING_EVENTS
    assert result.message == "1 cited event is gone."


def test_a_warning_rejects_an_empty_message() -> None:
    with pytest.raises(ValidationError):
        GenerationWarning(code=WarningCode.NO_EVENTS, message="")


def test_a_warning_rejects_an_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GenerationWarning(code=WarningCode.NO_EVENTS, message="x", level="high")


def test_no_warnings_is_full_confidence() -> None:
    assert assess_confidence([]) is Confidence.HIGH


def test_no_risks_alone_does_not_lower_confidence() -> None:
    # An all-clear picture is informational, not a gap.
    assert assess_confidence([warning(WarningCode.NO_RISKS)]) is Confidence.HIGH


@pytest.mark.parametrize("code", [WarningCode.NO_EVENTS, WarningCode.NO_TIMELINE])
def test_no_source_data_is_no_confidence(code: WarningCode) -> None:
    assert assess_confidence([warning(code)]) is Confidence.NONE


def test_missing_cited_evidence_is_low_confidence() -> None:
    assert assess_confidence([warning(WarningCode.MISSING_EVENTS)]) is Confidence.LOW


@pytest.mark.parametrize(
    "code",
    [WarningCode.EVENTS_OMITTED, WarningCode.MODEL_UNAVAILABLE, WarningCode.EMPTY_SUMMARY],
)
def test_a_partial_or_unphrased_picture_is_medium_confidence(code: WarningCode) -> None:
    assert assess_confidence([warning(code)]) is Confidence.MEDIUM


def test_the_most_severe_gap_decides_confidence() -> None:
    # No-data outranks a missing-evidence gap, which outranks a partial picture.
    warnings = [
        warning(WarningCode.EVENTS_OMITTED),
        warning(WarningCode.MISSING_EVENTS),
        warning(WarningCode.NO_TIMELINE),
    ]

    assert assess_confidence(warnings) is Confidence.NONE
    assert assess_confidence(warnings[:2]) is Confidence.LOW
    assert assess_confidence(warnings[:1]) is Confidence.MEDIUM
