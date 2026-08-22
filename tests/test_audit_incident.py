"""Tests for building generation audit records from an incident summary."""

from datetime import UTC, datetime, timedelta

from opsbrief.ai import AIProviderError, CompletionRequest, CompletionResponse, FakeAIProvider
from opsbrief.audit import GenerationKind, audit_incident_summary
from opsbrief.events import Event, EventInput
from opsbrief.incidents import (
    INCIDENT_SUMMARY_OUTPUT_VERSION,
    INCIDENT_SUMMARY_PROMPT_VERSION,
    Incident,
    IncidentSeverity,
    generate_incident_summary,
)

NOW = datetime(2026, 8, 22, 18, 0, tzinfo=UTC)


class FailingProvider:
    """A provider that always fails, standing in for an unavailable model."""

    name = "failing"

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        raise AIProviderError("transport failed")


def make_event(event_id: str, *, minutes_ago: int = 0, **overrides: object) -> Event:
    """Build a stored event with the given id and occurrence time."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Ticketing webhook failed ({event_id})",
        "occurred_at": NOW - timedelta(minutes=minutes_ago),
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def make_incident(event_ids: list[str], **overrides: object) -> Incident:
    """Declare an incident citing the given events."""
    payload: dict[str, object] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": IncidentSeverity.HIGH,
        "event_ids": event_ids,
        "at": NOW,
        "incident_id": "inc-1",
    }
    payload.update(overrides)
    return Incident.declare(**payload)


def test_a_summary_audit_names_the_incident_it_is_for() -> None:
    provider = FakeAIProvider(responses=["The webhook failed twice and is unresolved."])
    incident = make_incident(["e1", "e2"])
    events = [make_event("e1", minutes_ago=90), make_event("e2", minutes_ago=10)]

    audit = audit_incident_summary(generate_incident_summary(incident, events, provider))

    assert audit.kind is GenerationKind.INCIDENT_SUMMARY
    assert audit.subject_id == "inc-1"
    assert audit.model == "fake-1"
    assert audit.prompt_version == INCIDENT_SUMMARY_PROMPT_VERSION
    assert audit.output_version == INCIDENT_SUMMARY_OUTPUT_VERSION
    assert audit.source_event_ids == ["e1", "e2"]
    assert audit.source_event_count == 2
    assert audit.missing_event_ids == []


def test_a_summary_audit_reports_unresolved_citations_as_missing() -> None:
    provider = FakeAIProvider(responses=["The webhook failed and is unresolved."])
    incident = make_incident(["e1", "gone"])
    events = [make_event("e1", minutes_ago=30)]

    summary = generate_incident_summary(incident, events, provider)
    audit = audit_incident_summary(summary)

    assert audit.source_event_ids == ["e1", "gone"]
    # The missing ids read off the references agree with the summary's own list.
    assert audit.missing_event_ids == ["gone"]
    assert audit.missing_event_ids == summary.missing_event_ids


def test_a_summary_audit_carries_the_confidence_and_warnings() -> None:
    provider = FakeAIProvider(responses=["The webhook failed and is unresolved."])
    incident = make_incident(["e1", "gone"])
    events = [make_event("e1", minutes_ago=30)]

    summary = generate_incident_summary(incident, events, provider)
    audit = audit_incident_summary(summary)

    assert audit.confidence is summary.confidence
    assert audit.warning_codes == [warning.code for warning in summary.warnings]


def test_a_provider_outage_is_recorded_in_the_summary_audit() -> None:
    provider = FailingProvider()
    incident = make_incident(["e1"])
    events = [make_event("e1", minutes_ago=20)]

    summary = generate_incident_summary(incident, events, provider)
    audit = audit_incident_summary(summary)

    assert audit.model == provider.name
    assert audit.confidence is summary.confidence
    assert audit.warning_codes == [warning.code for warning in summary.warnings]
