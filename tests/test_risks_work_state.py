"""Tests for the work-state projection behind the overdue and blocked rules."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput
from opsbrief.risks.work_state import WorkState, group_work, work_key

NOW = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)


def make_event(
    event_id: str = "e1",
    *,
    received_at: datetime | None = None,
    **overrides: object,
) -> Event:
    """Return a stored event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    event = Event.from_input(EventInput(**payload), received_at=received_at)
    return event.model_copy(update={"id": event_id})


def test_work_key_is_source_type_and_id() -> None:
    event = make_event(source="tasks", entity_type="task", entity_id="M-1")

    assert work_key(event) == ("tasks", "task", "M-1")


def test_work_key_is_none_without_an_entity_pair() -> None:
    # The event contract forbids a half-set pair, so an event either carries both
    # entity fields or neither; an event with neither has no work key.
    assert work_key(make_event()) is None


def test_same_id_from_different_sources_is_a_different_key() -> None:
    first = make_event("a", source="tasks", entity_type="task", entity_id="M-1")
    second = make_event("b", source="rostering", entity_type="task", entity_id="M-1")

    assert work_key(first) != work_key(second)


def test_group_work_separates_keyed_from_unkeyed() -> None:
    keyed = make_event("k", entity_type="task", entity_id="M-1")
    unkeyed = make_event("u")

    states, independents = group_work([keyed, unkeyed])

    assert [state.key for state in states] == [("tasks", "task", "M-1")]
    assert [event.id for event in independents] == ["u"]


def test_current_state_is_the_latest_by_occurrence() -> None:
    first = make_event(
        "a", entity_type="task", entity_id="M-1", occurred_at=NOW - timedelta(hours=3)
    )
    second = make_event(
        "b", entity_type="task", entity_id="M-1", occurred_at=NOW - timedelta(hours=1)
    )

    [state], _ = group_work([second, first])

    assert state.current.id == "b"
    assert [event.id for event in state.events] == ["a", "b"]


def test_equal_occurrence_breaks_ties_by_receipt_then_id() -> None:
    occurred = NOW - timedelta(hours=2)
    early_receipt = make_event(
        "b",
        entity_type="task",
        entity_id="M-1",
        occurred_at=occurred,
        received_at=NOW - timedelta(minutes=30),
    )
    late_receipt = make_event(
        "a",
        entity_type="task",
        entity_id="M-1",
        occurred_at=occurred,
        received_at=NOW - timedelta(minutes=10),
    )

    [state], _ = group_work([early_receipt, late_receipt])

    assert state.current.id == "a"


def test_a_late_arriving_earlier_event_is_not_the_current_state() -> None:
    newer = make_event(
        "new",
        entity_type="task",
        entity_id="M-1",
        occurred_at=NOW - timedelta(hours=1),
        received_at=NOW - timedelta(hours=1),
    )
    stale = make_event(
        "old",
        entity_type="task",
        entity_id="M-1",
        occurred_at=NOW - timedelta(hours=5),
        received_at=NOW,
    )

    [state], _ = group_work([newer, stale])

    assert state.current.id == "new"


def test_is_cleared_reflects_the_current_status() -> None:
    blocked = make_event(
        "a",
        entity_type="task",
        entity_id="M-1",
        status="blocked",
        occurred_at=NOW - timedelta(hours=3),
    )
    resolved = make_event(
        "b",
        entity_type="task",
        entity_id="M-1",
        status="resolved",
        occurred_at=NOW - timedelta(hours=1),
    )

    [cleared], _ = group_work([blocked, resolved])
    [active], _ = group_work([blocked])

    assert cleared.is_cleared is True
    assert active.is_cleared is False


def test_blocked_run_start_is_the_start_of_the_current_block() -> None:
    open_event = make_event(
        "a",
        entity_type="task",
        entity_id="M-1",
        status="open",
        occurred_at=NOW - timedelta(hours=5),
    )
    first_block = make_event(
        "b",
        entity_type="task",
        entity_id="M-1",
        status="blocked",
        occurred_at=NOW - timedelta(hours=4),
    )
    still_block = make_event(
        "c",
        entity_type="task",
        entity_id="M-1",
        status="blocked",
        occurred_at=NOW - timedelta(hours=1),
    )

    [state], _ = group_work([open_event, first_block, still_block])
    start = state.blocked_run_start()

    assert start is not None
    assert start.id == "b"


def test_blocked_run_start_is_none_when_current_is_not_blocked() -> None:
    blocked = make_event(
        "a",
        entity_type="task",
        entity_id="M-1",
        status="blocked",
        occurred_at=NOW - timedelta(hours=3),
    )
    running = make_event(
        "b",
        entity_type="task",
        entity_id="M-1",
        status="in_progress",
        occurred_at=NOW - timedelta(hours=1),
    )

    [state], _ = group_work([blocked, running])

    assert state.blocked_run_start() is None


def test_a_reblock_after_clearing_starts_a_new_run() -> None:
    first_block = make_event(
        "a",
        entity_type="task",
        entity_id="M-1",
        status="blocked",
        occurred_at=NOW - timedelta(hours=5),
    )
    resolved = make_event(
        "b",
        entity_type="task",
        entity_id="M-1",
        status="resolved",
        occurred_at=NOW - timedelta(hours=3),
    )
    reblock = make_event(
        "c",
        entity_type="task",
        entity_id="M-1",
        status="blocked",
        occurred_at=NOW - timedelta(hours=1),
    )

    [state], _ = group_work([first_block, resolved, reblock])
    start = state.blocked_run_start()

    assert start is not None
    assert start.id == "c"


def test_states_are_ordered_by_key() -> None:
    a = make_event("a", entity_type="task", entity_id="M-2")
    b = make_event("b", entity_type="task", entity_id="M-1")

    states, _ = group_work([a, b])

    assert [state.key for state in states] == [
        ("tasks", "task", "M-1"),
        ("tasks", "task", "M-2"),
    ]


def test_work_state_current_reads_the_last_event() -> None:
    event = make_event("only", entity_type="task", entity_id="M-1")
    state = WorkState(key=("tasks", "task", "M-1"), events=(event,))

    assert state.current is event
