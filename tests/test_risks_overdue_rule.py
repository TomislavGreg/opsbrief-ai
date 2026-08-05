"""Tests for the overdue-work risk rule."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks import RiskRule, RiskSeverity, detect_risks
from opsbrief.risks.rules import OverdueWorkRule
from opsbrief.risks.rules.overdue import ESCALATION_AFTER

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def make_event(event_id: str = "e1", **overrides: object) -> Event:
    """Return a stored event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.due",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def test_rule_satisfies_the_protocol() -> None:
    assert isinstance(OverdueWorkRule(NOW), RiskRule)
    assert OverdueWorkRule(NOW).rule_id == "overdue_work"


def test_overdue_work_raises_a_traceable_risk() -> None:
    event = make_event(due_at=NOW - timedelta(hours=2))

    risks = OverdueWorkRule(NOW).evaluate([event])

    assert len(risks) == 1
    assert risks[0].rule == "overdue_work"
    assert risks[0].event_ids == ["e1"]
    assert "overdue" in risks[0].title.lower()


def test_work_not_yet_due_raises_nothing() -> None:
    event = make_event(due_at=NOW + timedelta(hours=1))

    assert OverdueWorkRule(NOW).evaluate([event]) == []


def test_no_events_raises_nothing() -> None:
    assert OverdueWorkRule(NOW).evaluate([]) == []


def test_resolved_work_raises_nothing() -> None:
    event = make_event(due_at=NOW - timedelta(days=3), status=EventStatus.RESOLVED)

    assert OverdueWorkRule(NOW).evaluate([event]) == []


def test_recently_overdue_work_is_medium() -> None:
    event = make_event(due_at=NOW - timedelta(hours=1))

    assert OverdueWorkRule(NOW).evaluate([event])[0].severity is RiskSeverity.MEDIUM


def test_long_overdue_work_is_high() -> None:
    event = make_event(due_at=NOW - timedelta(days=2))

    assert OverdueWorkRule(NOW).evaluate([event])[0].severity is RiskSeverity.HIGH


def test_escalation_boundary_is_high_exactly_at_the_threshold() -> None:
    # Exactly ESCALATION_AFTER late already counts as high, not medium.
    at_boundary = make_event("at", due_at=NOW - ESCALATION_AFTER)
    just_under = make_event("under", due_at=NOW - ESCALATION_AFTER + timedelta(seconds=1))

    assert OverdueWorkRule(NOW).evaluate([at_boundary])[0].severity is RiskSeverity.HIGH
    assert OverdueWorkRule(NOW).evaluate([just_under])[0].severity is RiskSeverity.MEDIUM


def test_risks_are_ordered_most_overdue_first() -> None:
    recent = make_event("recent", due_at=NOW - timedelta(hours=1))
    older = make_event("older", due_at=NOW - timedelta(days=2))
    oldest = make_event("oldest", due_at=NOW - timedelta(days=5))

    risks = OverdueWorkRule(NOW).evaluate([recent, oldest, older])

    assert [risk.event_ids[0] for risk in risks] == ["oldest", "older", "recent"]


def test_ties_on_deadline_break_by_event_id() -> None:
    due = NOW - timedelta(hours=3)
    first = make_event("aaa", due_at=due)
    second = make_event("bbb", due_at=due)

    risks = OverdueWorkRule(NOW).evaluate([second, first])

    assert [risk.event_ids[0] for risk in risks] == ["aaa", "bbb"]


def test_only_overdue_events_are_reported_among_a_mix() -> None:
    overdue = make_event("late", due_at=NOW - timedelta(hours=1))
    upcoming = make_event("soon", due_at=NOW + timedelta(hours=1))
    done = make_event("done", due_at=NOW - timedelta(days=1), status=EventStatus.RESOLVED)
    undated = make_event("undated")

    risks = OverdueWorkRule(NOW).evaluate([overdue, upcoming, done, undated])

    assert [risk.event_ids[0] for risk in risks] == ["late"]


def test_detection_is_deterministic() -> None:
    events = [make_event("e1", due_at=NOW - timedelta(hours=2)), make_event("e2")]
    rule = OverdueWorkRule(NOW)

    assert rule.evaluate(events) == rule.evaluate(events)


def test_title_stays_within_bounds_for_a_long_subject() -> None:
    event = make_event("long", subject="x" * 200, due_at=NOW - timedelta(hours=1))

    risk = OverdueWorkRule(NOW).evaluate([event])[0]

    assert len(risk.title) <= 200


def test_rule_plugs_into_the_detector() -> None:
    event = make_event(due_at=NOW - timedelta(hours=2))

    risks = detect_risks([event], [OverdueWorkRule(NOW)])

    assert [risk.rule for risk in risks] == ["overdue_work"]
