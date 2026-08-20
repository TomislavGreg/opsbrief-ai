"""Tests for generating an AI incident summary."""

from datetime import UTC, datetime, timedelta

from opsbrief.ai import AIProviderError, CompletionRequest, CompletionResponse, FakeAIProvider
from opsbrief.events import Event, EventInput
from opsbrief.incidents import (
    INCIDENT_SUMMARY_OUTPUT_VERSION,
    INCIDENT_SUMMARY_PROMPT_VERSION,
    MAX_INCIDENT_SUMMARY_LENGTH,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    generate_incident_summary,
)
from opsbrief.incidents.summary import DEFAULT_INCIDENT_INSTRUCTIONS

NOW = datetime(2026, 8, 14, 18, 0, tzinfo=UTC)


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


def test_scripted_summary_becomes_the_incident_summary() -> None:
    provider = FakeAIProvider(responses=["The ticketing webhook failed twice and is unresolved."])
    incident = make_incident(["e1", "e2"])
    events = [make_event("e1", minutes_ago=90), make_event("e2", minutes_ago=10)]

    result = generate_incident_summary(incident, events, provider)

    assert result.summary == "The ticketing webhook failed twice and is unresolved."
    assert result.model == "fake-1"
    assert result.incident_id == "inc-1"


def test_excluded_fields_are_held_back_from_the_provider() -> None:
    # An unscripted fake echoes the material it is shown, so the request material
    # is visible through what it records.
    provider = FakeAIProvider()
    incident = make_incident(["e1"])
    events = [make_event("e1", minutes_ago=20, subject="Steward Jane Doe did not report")]

    generate_incident_summary(incident, events, provider, excluded_fields={"subject"})

    material = provider.requests[0].input
    assert "Steward Jane Doe did not report" not in material
    assert "[excluded]" in material


def test_structured_facts_are_carried_from_the_incident_not_the_model() -> None:
    provider = FakeAIProvider(responses=["Anything here is only phrasing."])
    incident = make_incident(["e1", "e2"], severity=IncidentSeverity.CRITICAL)
    events = [make_event("e1", minutes_ago=90), make_event("e2", minutes_ago=10)]

    result = generate_incident_summary(incident, events, provider)

    assert result.title == "Ticketing integration failing repeatedly"
    assert result.status is IncidentStatus.OPEN
    assert result.severity is IncidentSeverity.CRITICAL
    # Cited order is preserved, so the summary traces to the incident's evidence.
    assert result.source_event_ids == ["e1", "e2"]
    assert result.started_at == NOW - timedelta(minutes=90)
    assert result.ended_at == NOW - timedelta(minutes=10)


def test_summary_carries_the_incidents_resolution_note() -> None:
    provider = FakeAIProvider(responses=["The webhook failed and was then restarted."])
    incident = make_incident(["e1"]).transition_to(
        IncidentStatus.RESOLVED, at=NOW, note="Restarted the ticketing sync."
    )

    result = generate_incident_summary(incident, [make_event("e1")], provider)

    assert result.status is IncidentStatus.RESOLVED
    assert result.resolution_note == "Restarted the ticketing sync."


def test_summary_has_no_resolution_note_for_an_active_incident() -> None:
    provider = FakeAIProvider(responses=["Still failing."])

    result = generate_incident_summary(make_incident(["e1"]), [make_event("e1")], provider)

    assert result.resolution_note is None


def test_generated_summary_records_the_prompt_and_output_versions() -> None:
    provider = FakeAIProvider(responses=["A summary."])

    result = generate_incident_summary(make_incident(["e1"]), [make_event("e1")], provider)

    assert result.prompt_version == INCIDENT_SUMMARY_PROMPT_VERSION
    assert result.output_version == INCIDENT_SUMMARY_OUTPUT_VERSION


def test_summary_is_collapsed_to_one_line() -> None:
    provider = FakeAIProvider(responses=["  line one\n\n   line   two\t"])

    result = generate_incident_summary(make_incident(["e1"]), [make_event("e1")], provider)

    assert result.summary == "line one line two"


def test_summary_is_truncated_to_the_bound() -> None:
    provider = FakeAIProvider(responses=["x" * (MAX_INCIDENT_SUMMARY_LENGTH + 50)])

    result = generate_incident_summary(make_incident(["e1"]), [make_event("e1")], provider)

    assert len(result.summary) == MAX_INCIDENT_SUMMARY_LENGTH


def test_an_empty_summary_still_yields_a_summary_and_is_noted() -> None:
    provider = FakeAIProvider(responses=["   \n  "])

    result = generate_incident_summary(make_incident(["e1"]), [make_event("e1")], provider)

    assert result.summary == ""
    assert result.source_event_ids == ["e1"]
    assert any("returned no summary" in note for note in result.notes)


def test_a_cited_event_that_no_longer_resolves_is_reported_and_noted() -> None:
    provider = FakeAIProvider(responses=["A summary."])
    incident = make_incident(["e1", "e2"])

    result = generate_incident_summary(incident, [make_event("e1", minutes_ago=20)], provider)

    assert result.missing_event_ids == ["e2"]
    assert any("no longer resolve" in note for note in result.notes)


def test_references_resolve_the_cited_events_in_cited_order() -> None:
    provider = FakeAIProvider(responses=["A summary."])
    incident = make_incident(["e1", "e2"])
    events = [
        make_event("e2", minutes_ago=10, subject="Second failure"),
        make_event("e1", minutes_ago=90, subject="First failure"),
    ]

    result = generate_incident_summary(incident, events, provider)

    # One reference per cited id, in cited order, matching source_event_ids.
    assert [reference.event_id for reference in result.references] == result.source_event_ids
    assert [reference.event_id for reference in result.references] == ["e1", "e2"]
    assert all(reference.resolved for reference in result.references)
    assert result.references[0].subject == "First failure"


def test_a_missing_cited_id_becomes_an_unresolved_reference() -> None:
    provider = FakeAIProvider(responses=["A summary."])
    incident = make_incident(["e1", "e2"])

    result = generate_incident_summary(incident, [make_event("e1", minutes_ago=20)], provider)

    by_id = {reference.event_id: reference for reference in result.references}
    assert [reference.event_id for reference in result.references] == ["e1", "e2"]
    assert by_id["e1"].resolved is True
    assert by_id["e2"].resolved is False
    assert by_id["e2"].subject is None


def test_the_request_is_bounded_and_records_the_rendered_material() -> None:
    provider = FakeAIProvider(responses=["ok"])
    incident = make_incident(["e1"])

    generate_incident_summary(incident, [make_event("e1")], provider, max_output_tokens=64)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.instructions == DEFAULT_INCIDENT_INSTRUCTIONS
    assert request.max_output_tokens == 64
    assert "Ticketing integration failing repeatedly" in request.input


def test_generating_a_summary_does_not_mutate_the_incident() -> None:
    provider = FakeAIProvider(responses=["A summary."])
    incident = make_incident(["e1", "e2"])

    generate_incident_summary(incident, [make_event("e1"), make_event("e2")], provider)

    assert incident.event_ids == ["e1", "e2"]
    assert incident.status is IncidentStatus.OPEN


class FailingProvider:
    """A provider that always fails, standing in for an unavailable model."""

    name = "failing"

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        raise AIProviderError("transport failed")


def test_a_provider_failure_degrades_to_the_deterministic_summary() -> None:
    # The model is only a phrasing layer, so an outage must not fail the summary:
    # the deterministic picture is still reported, with the summary left empty.
    incident = make_incident(["e1", "e2"])
    events = [make_event("e1", minutes_ago=90), make_event("e2", minutes_ago=10)]

    result = generate_incident_summary(incident, events, FailingProvider())

    assert result.summary == ""
    assert result.source_event_ids == ["e1", "e2"]
    assert result.started_at == NOW - timedelta(minutes=90)
    assert result.output_version == INCIDENT_SUMMARY_OUTPUT_VERSION
    assert result.prompt_version == INCIDENT_SUMMARY_PROMPT_VERSION
    assert any("unavailable" in note.lower() for note in result.notes)


def test_a_provider_failure_records_the_provider_as_the_model() -> None:
    # With no completion to name a model, the summary records the provider that was
    # asked, so a degraded summary still traces to where its prose should have come from.
    result = generate_incident_summary(make_incident(["e1"]), [make_event("e1")], FailingProvider())

    assert result.model == "failing"
