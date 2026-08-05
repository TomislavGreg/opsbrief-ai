"""Tests for overdue-work detection."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks.rules.overdue import is_overdue_work

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


def test_work_past_its_deadline_is_overdue() -> None:
    event = make_event(due_at=NOW - timedelta(minutes=1))

    assert is_overdue_work(event, NOW) is True


def test_work_before_its_deadline_is_not_overdue() -> None:
    event = make_event(due_at=NOW + timedelta(minutes=1))

    assert is_overdue_work(event, NOW) is False


def test_work_exactly_at_its_deadline_is_not_yet_overdue() -> None:
    # The deadline has to have passed, not merely arrived.
    event = make_event(due_at=NOW)

    assert is_overdue_work(event, NOW) is False


def test_work_without_a_deadline_is_never_overdue() -> None:
    event = make_event(due_at=None)

    assert is_overdue_work(event, NOW) is False


def test_resolved_work_is_not_overdue_even_past_its_deadline() -> None:
    event = make_event(due_at=NOW - timedelta(days=2), status=EventStatus.RESOLVED)

    assert is_overdue_work(event, NOW) is False


def test_cancelled_work_is_not_overdue_even_past_its_deadline() -> None:
    event = make_event(due_at=NOW - timedelta(days=2), status=EventStatus.CANCELLED)

    assert is_overdue_work(event, NOW) is False


def test_blocked_work_past_its_deadline_is_overdue() -> None:
    event = make_event(due_at=NOW - timedelta(hours=1), status=EventStatus.BLOCKED)

    assert is_overdue_work(event, NOW) is True


def test_failed_work_past_its_deadline_is_overdue() -> None:
    event = make_event(due_at=NOW - timedelta(hours=1), status=EventStatus.FAILED)

    assert is_overdue_work(event, NOW) is True
