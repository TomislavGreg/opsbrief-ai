"""Tests for the generation audit record contract."""

import pytest
from pydantic import ValidationError

from opsbrief.audit import GenerationAudit, GenerationKind
from opsbrief.warnings import Confidence, WarningCode


def make_audit(**overrides: object) -> GenerationAudit:
    """Build an audit record with sensible defaults, overridden per test."""
    payload: dict[str, object] = {
        "kind": GenerationKind.DAILY_BRIEF,
        "model": "fake-1",
        "prompt_version": "brief-prompt/1",
        "output_version": "daily-brief/3",
        "source_event_ids": ["e1", "e2"],
        "confidence": Confidence.HIGH,
    }
    payload.update(overrides)
    return GenerationAudit(**payload)


def test_a_record_carries_what_produced_the_output() -> None:
    audit = make_audit(
        source_event_ids=["e17", "e18"],
        warning_codes=[WarningCode.EVENTS_OMITTED],
        confidence=Confidence.MEDIUM,
    )

    assert audit.kind is GenerationKind.DAILY_BRIEF
    assert audit.model == "fake-1"
    assert audit.prompt_version == "brief-prompt/1"
    assert audit.output_version == "daily-brief/3"
    assert audit.source_event_ids == ["e17", "e18"]
    assert audit.warning_codes == [WarningCode.EVENTS_OMITTED]
    assert audit.confidence is Confidence.MEDIUM


def test_source_event_count_is_derived_from_the_ids() -> None:
    audit = make_audit(source_event_ids=["e1", "e2", "e3"])

    assert audit.source_event_count == 3


def test_source_event_count_tracks_an_empty_record() -> None:
    audit = make_audit(source_event_ids=[])

    assert audit.source_event_count == 0


def test_subject_id_defaults_to_absent() -> None:
    assert make_audit().subject_id is None


def test_subject_id_is_kept_for_an_incident_summary() -> None:
    audit = make_audit(kind=GenerationKind.INCIDENT_SUMMARY, subject_id="inc-1")

    assert audit.subject_id == "inc-1"


def test_a_blank_subject_id_is_refused() -> None:
    with pytest.raises(ValidationError):
        make_audit(subject_id="")


def test_a_blank_model_is_refused() -> None:
    with pytest.raises(ValidationError):
        make_audit(model="")


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        make_audit(generated_by="a-human")
