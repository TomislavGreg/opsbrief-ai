"""Tests for building generation audit records from generated output."""

from datetime import UTC, datetime

from opsbrief.ai import (
    AIProviderError,
    CompletionRequest,
    CompletionResponse,
    FakeAIProvider,
)
from opsbrief.audit import GenerationKind, audit_daily_brief
from opsbrief.brief import BriefContext, EventDigest
from opsbrief.brief.generate import generate_brief
from opsbrief.brief.schema import BRIEF_OUTPUT_VERSION, BRIEF_PROMPT_VERSION
from opsbrief.events import EventSeverity, EventStatus
from opsbrief.references import SourceReference
from opsbrief.risks import Risk, RiskSeverity

NOW = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


class FailingProvider:
    """A provider that always fails, standing in for an unavailable model."""

    name = "failing"

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        raise AIProviderError("transport failed")


def make_risk(*, event_ids: list[str]) -> Risk:
    """Build an overdue-work risk citing the given events."""
    return Risk(
        rule="overdue_work",
        title="Safety inspection for North Stand is overdue",
        detail="Work was due earlier and is not resolved.",
        severity=RiskSeverity.HIGH,
        event_ids=event_ids,
    )


def make_context(
    *,
    risks: list[Risk] | None = None,
    references: list[SourceReference] | None = None,
    notes: list[str] | None = None,
) -> BriefContext:
    """Build a brief context for audit tests, with references and notes settable."""
    return BriefContext(
        generated_at=NOW,
        event_count=1,
        risks=risks if risks is not None else [make_risk(event_ids=["e04"])],
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
        references=references if references is not None else [SourceReference.unresolved("e04")],
        notes=notes if notes is not None else [],
    )


def test_a_brief_audit_names_what_produced_it() -> None:
    context = make_context(references=[SourceReference.unresolved("e04")])
    provider = FakeAIProvider(responses=["One inspection is overdue."])

    audit = audit_daily_brief(generate_brief(context, provider))

    assert audit.kind is GenerationKind.DAILY_BRIEF
    assert audit.subject_id is None
    assert audit.model == "fake-1"
    assert audit.prompt_version == BRIEF_PROMPT_VERSION
    assert audit.output_version == BRIEF_OUTPUT_VERSION
    assert audit.source_event_ids == ["e04"]
    assert audit.source_event_count == 1


def test_a_brief_audit_reports_unresolved_citations_as_missing() -> None:
    references = [
        SourceReference(
            event_id="e04",
            resolved=True,
            source="safety",
            event_type="inspection.overdue",
            subject="Safety inspection for North Stand is overdue",
            occurred_at=NOW,
            severity=EventSeverity.HIGH,
            status=EventStatus.OVERDUE,
        ),
        SourceReference.unresolved("gone"),
    ]
    context = make_context(
        risks=[make_risk(event_ids=["e04", "gone"])],
        references=references,
    )
    provider = FakeAIProvider(responses=["One inspection is overdue."])

    audit = audit_daily_brief(generate_brief(context, provider))

    assert audit.source_event_ids == ["e04", "gone"]
    assert audit.missing_event_ids == ["gone"]


def test_a_brief_audit_carries_the_confidence_and_warnings() -> None:
    # An empty context yields a no-events warning and none-confidence brief.
    context = BriefContext(generated_at=NOW, event_count=0, risks=[], recent_events=[])
    provider = FakeAIProvider(responses=["Nothing to report."])

    brief = generate_brief(context, provider)
    audit = audit_daily_brief(brief)

    assert audit.confidence is brief.confidence
    assert audit.warning_codes == [warning.code for warning in brief.warnings]
    assert audit.source_event_ids == []
    assert audit.missing_event_ids == []


def test_a_provider_outage_is_recorded_in_the_brief_audit() -> None:
    provider = FailingProvider()

    brief = generate_brief(make_context(), provider)
    audit = audit_daily_brief(brief)

    assert audit.model == provider.name
    assert audit.confidence is brief.confidence
    assert audit.warning_codes == [warning.code for warning in brief.warnings]
