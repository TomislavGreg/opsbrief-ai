"""Tests for generating a structured daily brief from a context."""

from datetime import UTC, datetime

from opsbrief.ai import AIProviderError, CompletionRequest, CompletionResponse, FakeAIProvider
from opsbrief.brief import (
    BRIEF_OUTPUT_VERSION,
    BRIEF_PROMPT_VERSION,
    MAX_SUMMARY_LENGTH,
    BriefContext,
    EventDigest,
)
from opsbrief.brief.generate import DEFAULT_INSTRUCTIONS, generate_brief, render_context
from opsbrief.events import EventSeverity, EventStatus
from opsbrief.risks import Risk, RiskSeverity

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def make_context(
    *, risks: list[Risk] | None = None, notes: list[str] | None = None
) -> BriefContext:
    """Build a small brief context for generation tests."""
    return BriefContext(
        generated_at=NOW,
        event_count=2,
        risks=risks if risks is not None else [make_risk()],
        recent_events=[
            EventDigest(
                id="e04",
                source="safety",
                event_type="inspection.overdue",
                subject="Safety inspection for North Stand is overdue",
                occurred_at=NOW,
                severity=EventSeverity.HIGH,
                status=EventStatus.OVERDUE,
            )
        ],
        notes=notes if notes is not None else [],
    )


def make_risk() -> Risk:
    return Risk(
        rule="overdue_work",
        title="Safety inspection for North Stand is overdue",
        detail="Work was due earlier and is not resolved.",
        severity=RiskSeverity.HIGH,
        event_ids=["e04"],
    )


def test_scripted_summary_becomes_the_brief_summary() -> None:
    provider = FakeAIProvider(responses=["One safety inspection is overdue; handle it first."])

    brief = generate_brief(make_context(), provider)

    assert brief.summary == "One safety inspection is overdue; handle it first."
    assert brief.model == "fake-1"


def test_structured_facts_are_carried_from_the_context_not_the_model() -> None:
    context = make_context(notes=["Showing the 1 most recent of 9 events."])
    provider = FakeAIProvider(responses=["Anything the model says here is only phrasing."])

    brief = generate_brief(context, provider)

    assert brief.generated_at == context.generated_at
    assert brief.risks == context.risks
    assert brief.source_event_ids == context.source_event_ids == ["e04"]
    assert brief.notes == ["Showing the 1 most recent of 9 events."]


def test_generated_brief_records_the_prompt_and_output_versions() -> None:
    provider = FakeAIProvider(responses=["A summary."])

    brief = generate_brief(make_context(), provider)

    assert brief.prompt_version == BRIEF_PROMPT_VERSION
    assert brief.output_version == BRIEF_OUTPUT_VERSION


def test_versions_are_recorded_even_when_the_summary_is_missing() -> None:
    provider = FakeAIProvider(responses=["   "])

    brief = generate_brief(make_context(), provider)

    assert brief.summary == ""
    assert brief.prompt_version == BRIEF_PROMPT_VERSION
    assert brief.output_version == BRIEF_OUTPUT_VERSION


def test_summary_is_collapsed_to_one_line() -> None:
    provider = FakeAIProvider(responses=["  line one\n\n   line   two\t"])

    brief = generate_brief(make_context(), provider)

    assert brief.summary == "line one line two"


def test_summary_is_truncated_to_the_bound() -> None:
    provider = FakeAIProvider(responses=["x" * (MAX_SUMMARY_LENGTH + 50)])

    brief = generate_brief(make_context(), provider)

    assert len(brief.summary) == MAX_SUMMARY_LENGTH


def test_an_empty_summary_still_yields_a_brief_and_is_noted() -> None:
    provider = FakeAIProvider(responses=["   \n  "])

    brief = generate_brief(make_context(notes=["existing note"]), provider)

    assert brief.summary == ""
    assert brief.risks == [make_risk()]
    assert "existing note" in brief.notes
    assert any("returned no summary" in note for note in brief.notes)


def test_the_request_is_bounded_and_records_the_rendered_context() -> None:
    provider = FakeAIProvider(responses=["ok"])

    generate_brief(make_context(), provider, max_output_tokens=64)

    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.instructions == DEFAULT_INSTRUCTIONS
    assert request.max_output_tokens == 64
    assert "Safety inspection for North Stand is overdue" in request.input


class FailingProvider:
    """A provider that always fails, standing in for an unavailable model."""

    name = "failing"

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        raise AIProviderError("transport failed")


def test_a_provider_failure_degrades_to_the_deterministic_brief() -> None:
    # The model is only a phrasing layer, so an outage must not fail the brief:
    # the deterministic picture is still reported, with the summary left empty.
    risk = make_risk()

    brief = generate_brief(make_context(risks=[risk]), FailingProvider())

    assert brief.summary == ""
    assert brief.risks == [risk]
    assert brief.source_event_ids == ["e04"]
    assert brief.output_version == BRIEF_OUTPUT_VERSION
    assert brief.prompt_version == BRIEF_PROMPT_VERSION
    assert any("unavailable" in note.lower() for note in brief.notes)


def test_a_provider_failure_records_the_provider_as_the_model() -> None:
    # With no completion to name a model, the brief records the provider that was
    # asked, so a degraded brief still traces to where its summary should have come from.
    brief = generate_brief(make_context(), FailingProvider())

    assert brief.model == "failing"


def test_render_context_lists_risks_events_and_notes() -> None:
    rendered = render_context(make_context(notes=["No older events."]))

    assert "Operational picture as of 2026-08-09T12:00:00+00:00." in rendered
    assert "2 events recorded." in rendered
    assert (
        "[high] Safety inspection for North Stand is overdue (overdue_work; events: e04)"
        in rendered
    )
    assert "safety inspection.overdue" in rendered
    assert "Notes:" in rendered
    assert "- No older events." in rendered


def test_render_context_says_none_when_there_are_no_risks() -> None:
    rendered = render_context(make_context(risks=[]))

    assert "Risks (most urgent first): none." in rendered
