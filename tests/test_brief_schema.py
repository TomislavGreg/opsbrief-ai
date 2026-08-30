"""Tests for the daily-brief context contract."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opsbrief.brief import BriefContext, EventDigest
from opsbrief.events import EventSeverity, EventStatus
from opsbrief.risks import Risk, RiskSeverity

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def make_digest(event_id: str, **overrides: object) -> EventDigest:
    """Build an event digest with sensible defaults for the given id."""
    payload: dict[str, object] = {
        "id": event_id,
        "source": "tasks",
        "event_type": "task.update",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW,
        "severity": EventSeverity.INFO,
    }
    payload.update(overrides)
    return EventDigest(**payload)


def make_risk(rule: str, event_ids: list[str], severity: RiskSeverity = RiskSeverity.HIGH) -> Risk:
    """Build a risk citing the given rule and events."""
    return Risk(
        rule=rule,
        title=f"{rule} fired",
        detail=f"{rule} fired over {event_ids}",
        severity=severity,
        event_ids=event_ids,
    )


def test_digest_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EventDigest(
            id="e1",
            source="tasks",
            event_type="task.update",
            subject="Work item e1",
            occurred_at=NOW,
            severity=EventSeverity.INFO,
            metadata={"leaked": True},
        )


def test_digest_status_is_optional() -> None:
    digest = make_digest("e1")

    assert digest.status is None
    assert make_digest("e2", status=EventStatus.BLOCKED).status is EventStatus.BLOCKED


def test_context_collects_source_event_ids_risks_first() -> None:
    context = BriefContext(
        generated_at=NOW,
        event_count=3,
        risks=[make_risk("overdue_work", ["e2"])],
        recent_events=[make_digest("e1"), make_digest("e2"), make_digest("e3")],
    )

    # The risk's event comes first, then recent events not already cited.
    assert context.source_event_ids == ["e2", "e1", "e3"]


def test_context_source_event_ids_are_distinct() -> None:
    context = BriefContext(
        generated_at=NOW,
        event_count=2,
        risks=[make_risk("overdue_work", ["e1"]), make_risk("blocked_work", ["e1", "e2"])],
        recent_events=[make_digest("e1"), make_digest("e2")],
    )

    assert context.source_event_ids == ["e1", "e2"]


def test_context_suggests_one_next_action_per_risk_in_order() -> None:
    context = BriefContext(
        generated_at=NOW,
        event_count=2,
        risks=[
            make_risk("repeated_integration_failure", ["e1"], RiskSeverity.CRITICAL),
            make_risk("overdue_work", ["e2"], RiskSeverity.HIGH),
        ],
        recent_events=[make_digest("e1"), make_digest("e2")],
    )

    actions = context.next_actions
    assert [a.rule for a in actions] == ["repeated_integration_failure", "overdue_work"]
    assert actions[0].event_ids == ["e1"]
    assert actions[1].severity is RiskSeverity.HIGH


def test_context_with_no_risks_suggests_no_actions() -> None:
    context = BriefContext(
        generated_at=NOW,
        event_count=1,
        risks=[],
        recent_events=[make_digest("e1")],
    )

    assert context.next_actions == []


def test_context_with_no_events_is_valid_and_cites_nothing() -> None:
    context = BriefContext(
        generated_at=NOW,
        event_count=0,
        risks=[],
        recent_events=[],
        notes=["No operational events have been recorded."],
    )

    assert context.event_count == 0
    assert context.source_event_ids == []
    assert context.notes == ["No operational events have been recorded."]


def test_context_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        BriefContext(
            generated_at=NOW,
            event_count=0,
            risks=[],
            recent_events=[],
            summary="phrased by a model",
        )
