"""Tests for blocked-work detection."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks.rules.blocked import is_blocked_work

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def make_event(event_id: str = "e1", **overrides: object) -> Event:
    """Return a stored event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.blocked",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def test_blocked_work_is_blocked() -> None:
    event = make_event(status=EventStatus.BLOCKED)

    assert is_blocked_work(event) is True


def test_work_without_a_status_is_not_blocked() -> None:
    event = make_event(status=None)

    assert is_blocked_work(event) is False


def test_open_work_is_not_blocked() -> None:
    event = make_event(status=EventStatus.OPEN)

    assert is_blocked_work(event) is False


def test_in_progress_work_is_not_blocked() -> None:
    event = make_event(status=EventStatus.IN_PROGRESS)

    assert is_blocked_work(event) is False


def test_resolved_work_is_not_blocked() -> None:
    # Even work that was once blocked and is now resolved no longer counts.
    event = make_event(status=EventStatus.RESOLVED)

    assert is_blocked_work(event) is False


def test_blocked_status_is_recognised_regardless_of_deadline() -> None:
    # Blocked work is a concern with or without a deadline attached.
    with_deadline = make_event(status=EventStatus.BLOCKED, due_at=NOW + timedelta(days=1))
    without_deadline = make_event(status=EventStatus.BLOCKED)

    assert is_blocked_work(with_deadline) is True
    assert is_blocked_work(without_deadline) is True
