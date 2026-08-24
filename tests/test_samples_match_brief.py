"""Tests for the worked match-operations daily brief example."""

from opsbrief.ai import FakeAIProvider
from opsbrief.brief import BRIEF_OUTPUT_VERSION, Confidence, DailyBrief
from opsbrief.samples import (
    SAMPLE_MATCH_BRIEF_AT,
    SAMPLE_MATCH_BRIEF_SUMMARY,
    build_sample_match_brief,
    load_sample_match_stored_events,
)


def test_example_is_a_daily_brief_for_the_fixed_instant() -> None:
    brief = build_sample_match_brief()

    assert isinstance(brief, DailyBrief)
    assert brief.generated_at == SAMPLE_MATCH_BRIEF_AT
    assert brief.output_version == BRIEF_OUTPUT_VERSION


def test_example_uses_the_scripted_summary_by_default() -> None:
    brief = build_sample_match_brief()

    assert brief.summary == SAMPLE_MATCH_BRIEF_SUMMARY
    assert brief.model == "fake-1"


def test_example_surfaces_the_match_day_risks() -> None:
    brief = build_sample_match_brief()

    rules = {risk.rule for risk in brief.risks}
    assert rules == {"repeated_integration_failure", "blocked_work", "overdue_work"}
    # Severity leads the ordering, so the failing broadcast feed comes first.
    assert brief.risks[0].rule == "repeated_integration_failure"
    assert brief.risks[0].severity.value == "high"


def test_example_traces_every_risk_back_to_fixture_events() -> None:
    brief = build_sample_match_brief()
    known_ids = {event.id for event in load_sample_match_stored_events()}

    for risk in brief.risks:
        assert risk.event_ids
        assert set(risk.event_ids) <= known_ids


def test_example_is_a_complete_picture() -> None:
    brief = build_sample_match_brief()

    # Every fixture event is described and resolves, so nothing is missing or
    # omitted and the picture is phrased: the brief is high confidence.
    assert brief.warnings == []
    assert brief.notes == []
    assert brief.confidence is Confidence.HIGH
    assert brief.references
    assert all(reference.resolved for reference in brief.references)


def test_example_is_deterministic() -> None:
    first = build_sample_match_brief()
    second = build_sample_match_brief()

    assert first.model_dump() == second.model_dump()


def test_a_caller_can_phrase_the_same_picture_differently() -> None:
    provider = FakeAIProvider(responses=["All quiet ahead of kickoff."])

    brief = build_sample_match_brief(provider)

    # The provider only phrases; the deterministic picture is unchanged.
    assert brief.summary == "All quiet ahead of kickoff."
    assert {risk.rule for risk in brief.risks} == {
        "repeated_integration_failure",
        "blocked_work",
        "overdue_work",
    }
