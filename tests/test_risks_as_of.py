"""The single as-of boundary the risk picture is judged against.

Every rule and the brief context judge the picture as of one reference instant.
An event occurring after that instant is a future report: it describes something
that has not happened yet, so it can neither raise nor clear a present risk nor
appear as recent activity, and advancing the reference past it admits it like any
other event. These tests pin that boundary across the rules and the brief context
and confirm it is an occurrence-time boundary, not a receipt-time one.
"""

from datetime import UTC, datetime, timedelta

from opsbrief.brief.context import build_brief_context
from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks import (
    BlockedWorkRule,
    OverdueWorkRule,
    RepeatedIntegrationFailureRule,
    RiskSeverity,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def make_event(event_id: str, **overrides: object) -> Event:
    """Return a stored event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def work(event_id: str, **overrides: object) -> Event:
    """Return a stored event naming a stable work entity, so reports correlate."""
    payload: dict[str, object] = {"entity_type": "task", "entity_id": "task-1"}
    payload.update(overrides)
    return make_event(event_id, **payload)


# --- Overdue: a future resolution must not clear present overdue work. ----------


def test_a_future_resolution_does_not_clear_present_overdue_work() -> None:
    events = [
        work("open", occurred_at=NOW - timedelta(days=2), due_at=NOW - timedelta(days=1)),
        work("done", occurred_at=NOW + timedelta(hours=1), status=EventStatus.RESOLVED),
    ]

    risks = OverdueWorkRule(NOW).evaluate(events)

    assert [risk.event_ids for risk in risks] == [["open"]]


def test_advancing_the_reference_admits_the_resolution_and_clears_overdue() -> None:
    events = [
        work("open", occurred_at=NOW - timedelta(days=2), due_at=NOW - timedelta(days=1)),
        work("done", occurred_at=NOW + timedelta(hours=1), status=EventStatus.RESOLVED),
    ]

    later = NOW + timedelta(hours=2)
    assert OverdueWorkRule(later).evaluate(events) == []


def test_a_future_reschedule_does_not_clear_present_overdue_work() -> None:
    events = [
        work("open", occurred_at=NOW - timedelta(days=2), due_at=NOW - timedelta(days=1)),
        work("push", occurred_at=NOW + timedelta(hours=1), due_at=NOW + timedelta(days=5)),
    ]

    risks = OverdueWorkRule(NOW).evaluate(events)

    assert [risk.event_ids for risk in risks] == [["open"]]


# --- Blocked: future reports must neither clear nor invent a present block. -----


def test_a_future_resolution_does_not_clear_a_present_block() -> None:
    events = [
        work("block", occurred_at=NOW - timedelta(days=2), status=EventStatus.BLOCKED),
        work("done", occurred_at=NOW + timedelta(hours=1), status=EventStatus.RESOLVED),
    ]

    risks = BlockedWorkRule(NOW).evaluate(events)

    assert [risk.event_ids for risk in risks] == [["block"]]
    assert risks[0].severity is RiskSeverity.HIGH


def test_a_future_block_does_not_raise_a_present_risk() -> None:
    events = [work("block", occurred_at=NOW + timedelta(hours=1), status=EventStatus.BLOCKED)]

    assert BlockedWorkRule(NOW).evaluate(events) == []
    # Once the reference reaches the block it is admitted like any other report.
    assert BlockedWorkRule(NOW + timedelta(hours=2)).evaluate(events)[0].event_ids == ["block"]


# --- Integration: a scheduled recovery must not clear a standing run. -----------


def failure(event_id: str, *, ago: timedelta) -> Event:
    """Return an integration failure ``ago`` before NOW."""
    return make_event(
        event_id,
        source="integrations",
        event_type="integration.failed",
        status=EventStatus.FAILED,
        entity_type="integration",
        entity_id="ticketing",
        occurred_at=NOW - ago,
    )


def test_a_future_recovery_does_not_clear_current_integration_failures() -> None:
    events = [
        failure("f1", ago=timedelta(hours=3)),
        failure("f2", ago=timedelta(hours=2)),
        failure("f3", ago=timedelta(hours=1)),
        make_event(
            "rec",
            source="integrations",
            event_type="integration.recovered",
            status=EventStatus.RESOLVED,
            entity_type="integration",
            entity_id="ticketing",
            occurred_at=NOW + timedelta(hours=1),
        ),
    ]

    risks = RepeatedIntegrationFailureRule(NOW).evaluate(events)

    assert len(risks) == 1
    assert risks[0].event_ids == ["f1", "f2", "f3"]


# --- Brief context: future events are not counted or shown as recent activity. --


def test_the_brief_context_excludes_future_events_from_the_picture() -> None:
    events = [
        make_event("past", occurred_at=NOW - timedelta(hours=1)),
        make_event("future", occurred_at=NOW + timedelta(hours=1)),
    ]

    context = build_brief_context(events, NOW)

    assert context.event_count == 1
    assert [digest.id for digest in context.recent_events] == ["past"]


def test_advancing_the_reference_admits_a_future_event_to_the_context() -> None:
    events = [
        make_event("past", occurred_at=NOW - timedelta(hours=1)),
        make_event("later", occurred_at=NOW + timedelta(hours=1)),
    ]

    context = build_brief_context(events, NOW + timedelta(hours=2))

    assert context.event_count == 2
    assert [digest.id for digest in context.recent_events] == ["later", "past"]


# --- Old unresolved work stays visible despite the bounded recent view. ---------


def test_old_unresolved_work_stays_a_risk_below_a_short_recent_window() -> None:
    # One old overdue task, then many newer unrelated events that fill the bounded
    # recent view. The overdue risk is judged over the whole past history, so it is
    # still raised even though the old event is pushed out of the recent-events cap.
    events = [work("old", occurred_at=NOW - timedelta(days=5), due_at=NOW - timedelta(days=4))]
    events += [make_event(f"n{i}", occurred_at=NOW - timedelta(hours=i + 1)) for i in range(5)]

    context = build_brief_context(events, NOW, max_recent_events=3)

    assert len(context.recent_events) == 3
    assert "old" not in {digest.id for digest in context.recent_events}
    assert [risk.event_ids for risk in context.risks] == [["old"]]
