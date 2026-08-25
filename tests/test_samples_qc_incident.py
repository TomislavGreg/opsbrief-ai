"""Tests for the worked quality-control incident example."""

from opsbrief.ai import FakeAIProvider
from opsbrief.incidents import (
    INCIDENT_SUMMARY_OUTPUT_VERSION,
    Confidence,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentSummary,
)
from opsbrief.samples import (
    SAMPLE_QC_EVENT_ID,
    SAMPLE_QC_INCIDENT_DECLARED_AT,
    SAMPLE_QC_INCIDENT_ID,
    SAMPLE_QC_INCIDENT_RESOLVED_AT,
    SAMPLE_QC_INCIDENT_SUMMARY,
    SAMPLE_QC_RESOLUTION_NOTE,
    build_sample_qc_incident,
    build_sample_qc_incident_summary,
    load_sample_match_stored_events,
)


def test_incident_is_declared_from_the_rejected_calibration_check() -> None:
    incident = build_sample_qc_incident()

    assert isinstance(incident, Incident)
    assert incident.id == SAMPLE_QC_INCIDENT_ID
    assert incident.severity is IncidentSeverity.HIGH
    assert incident.event_ids == [SAMPLE_QC_EVENT_ID]


def test_incident_walks_through_the_lifecycle_to_resolved() -> None:
    incident = build_sample_qc_incident()

    assert incident.status is IncidentStatus.RESOLVED
    assert incident.is_active is False
    assert incident.opened_at == SAMPLE_QC_INCIDENT_DECLARED_AT
    assert incident.resolved_at == SAMPLE_QC_INCIDENT_RESOLVED_AT
    assert incident.resolution_note == SAMPLE_QC_RESOLUTION_NOTE


def test_incident_cites_a_fixture_event() -> None:
    incident = build_sample_qc_incident()
    known_ids = {event.id for event in load_sample_match_stored_events()}

    assert set(incident.event_ids) <= known_ids


def test_incident_is_deterministic() -> None:
    first = build_sample_qc_incident()
    second = build_sample_qc_incident()

    assert first.model_dump() == second.model_dump()


def test_summary_carries_the_deterministic_incident_picture() -> None:
    summary = build_sample_qc_incident_summary()

    assert isinstance(summary, IncidentSummary)
    assert summary.status is IncidentStatus.RESOLVED
    assert summary.severity is IncidentSeverity.HIGH
    assert summary.resolution_note == SAMPLE_QC_RESOLUTION_NOTE
    assert summary.source_event_ids == [SAMPLE_QC_EVENT_ID]
    assert summary.output_version == INCIDENT_SUMMARY_OUTPUT_VERSION


def test_summary_uses_the_scripted_text_by_default() -> None:
    summary = build_sample_qc_incident_summary()

    assert summary.summary == SAMPLE_QC_INCIDENT_SUMMARY
    assert summary.model == "fake-1"


def test_summary_is_a_complete_picture() -> None:
    summary = build_sample_qc_incident_summary()

    # The cited calibration check resolves against the fixture and the picture is
    # phrased, so nothing is missing and the summary is high confidence.
    assert summary.missing_event_ids == []
    assert summary.warnings == []
    assert summary.notes == []
    assert summary.confidence is Confidence.HIGH
    assert summary.references
    assert all(reference.resolved for reference in summary.references)


def test_summary_spans_the_cited_event() -> None:
    summary = build_sample_qc_incident_summary()
    events = {event.id for event in load_sample_match_stored_events()}

    assert SAMPLE_QC_EVENT_ID in events
    # A single cited event, so the span starts and ends at the same instant.
    assert summary.started_at is not None
    assert summary.started_at == summary.ended_at


def test_summary_is_deterministic() -> None:
    first = build_sample_qc_incident_summary()
    second = build_sample_qc_incident_summary()

    assert first.model_dump() == second.model_dump()


def test_a_caller_can_phrase_the_same_picture_differently() -> None:
    provider = FakeAIProvider(responses=["Goal-line check recalibrated and signed off."])

    summary = build_sample_qc_incident_summary(provider)

    # The provider only phrases; the deterministic picture is unchanged.
    assert summary.summary == "Goal-line check recalibrated and signed off."
    assert summary.status is IncidentStatus.RESOLVED
    assert summary.source_event_ids == [SAMPLE_QC_EVENT_ID]
