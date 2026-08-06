"""Tests for the blocked-work risk rule."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks import BlockedWorkRule, RiskRule, RiskSeverity, detect_risks
from opsbrief.risks.rules.blocked import ESCALATION_AFTER

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def make_event(event_id: str = "e1", **overrides: object) -> Event:
    """Return a stored blocked event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.blocked",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=2),
        "status": EventStatus.BLOCKED,
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def test_rule_satisfies_the_protocol() -> None:
    assert isinstance(BlockedWorkRule(NOW), RiskRule)
    assert BlockedWorkRule(NOW).rule_id == "blocked_work"


def test_blocked_work_raises_a_traceable_risk() -> None:
    event = make_event()

    risks = BlockedWorkRule(NOW).evaluate([event])

    assert len(risks) == 1
    assert risks[0].rule == "blocked_work"
    assert risks[0].event_ids == ["e1"]
    assert "blocked" in risks[0].title.lower()


def test_unblocked_work_raises_nothing() -> None:
    event = make_event(status=EventStatus.IN_PROGRESS)

    assert BlockedWorkRule(NOW).evaluate([event]) == []


def test_no_events_raises_nothing() -> None:
    assert BlockedWorkRule(NOW).evaluate([]) == []


def test_blocked_work_without_a_deadline_still_raises() -> None:
    event = make_event(due_at=None)

    assert len(BlockedWorkRule(NOW).evaluate([event])) == 1


def test_recently_blocked_work_is_medium() -> None:
    event = make_event(occurred_at=NOW - timedelta(hours=1))

    assert BlockedWorkRule(NOW).evaluate([event])[0].severity is RiskSeverity.MEDIUM


def test_long_blocked_work_is_high() -> None:
    event = make_event(occurred_at=NOW - timedelta(days=2))

    assert BlockedWorkRule(NOW).evaluate([event])[0].severity is RiskSeverity.HIGH


def test_escalation_boundary_is_high_exactly_at_the_threshold() -> None:
    # Exactly ESCALATION_AFTER blocked already counts as high, not medium.
    at_boundary = make_event("at", occurred_at=NOW - ESCALATION_AFTER)
    just_under = make_event("under", occurred_at=NOW - ESCALATION_AFTER + timedelta(seconds=1))

    assert BlockedWorkRule(NOW).evaluate([at_boundary])[0].severity is RiskSeverity.HIGH
    assert BlockedWorkRule(NOW).evaluate([just_under])[0].severity is RiskSeverity.MEDIUM


def test_risks_are_ordered_longest_blocked_first() -> None:
    recent = make_event("recent", occurred_at=NOW - timedelta(hours=1))
    older = make_event("older", occurred_at=NOW - timedelta(days=2))
    oldest = make_event("oldest", occurred_at=NOW - timedelta(days=5))

    risks = BlockedWorkRule(NOW).evaluate([recent, oldest, older])

    assert [risk.event_ids[0] for risk in risks] == ["oldest", "older", "recent"]


def test_ties_on_blocked_since_break_by_event_id() -> None:
    since = NOW - timedelta(hours=3)
    first = make_event("aaa", occurred_at=since)
    second = make_event("bbb", occurred_at=since)

    risks = BlockedWorkRule(NOW).evaluate([second, first])

    assert [risk.event_ids[0] for risk in risks] == ["aaa", "bbb"]


def test_only_blocked_events_are_reported_among_a_mix() -> None:
    blocked = make_event("stuck")
    running = make_event("running", status=EventStatus.IN_PROGRESS)
    done = make_event("done", status=EventStatus.RESOLVED)
    unset = make_event("unset", status=None)

    risks = BlockedWorkRule(NOW).evaluate([blocked, running, done, unset])

    assert [risk.event_ids[0] for risk in risks] == ["stuck"]


def test_detection_is_deterministic() -> None:
    events = [make_event("e1"), make_event("e2", status=EventStatus.OPEN)]
    rule = BlockedWorkRule(NOW)

    assert rule.evaluate(events) == rule.evaluate(events)


def test_title_stays_within_bounds_for_a_long_subject() -> None:
    event = make_event("long", subject="x" * 200)

    risk = BlockedWorkRule(NOW).evaluate([event])[0]

    assert len(risk.title) <= 200


def test_rule_plugs_into_the_detector() -> None:
    event = make_event()

    risks = detect_risks([event], [BlockedWorkRule(NOW)])

    assert [risk.rule for risk in risks] == ["blocked_work"]


def test_detector_runs_blocked_and_overdue_rules_together() -> None:
    from opsbrief.risks import OverdueWorkRule

    blocked = make_event("blocked")
    overdue = make_event("overdue", status=EventStatus.OPEN, due_at=NOW - timedelta(hours=1))

    risks = detect_risks([blocked, overdue], [OverdueWorkRule(NOW), BlockedWorkRule(NOW)])

    assert {risk.rule for risk in risks} == {"overdue_work", "blocked_work"}
