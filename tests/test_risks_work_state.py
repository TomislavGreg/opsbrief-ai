"""Tests for the work-state projection behind the overdue and blocked rules."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks.work_state import group_work, is_informational, work_key

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


def keyed(event_id: str, **overrides: object) -> Event:
    """Return an event carrying the shared entity pair, so it groups by work key."""
    return make_event(event_id, entity_type="task", entity_id="M-1", **overrides)


def only_state(events: list[Event]):
    """Group ``events`` and return the single expected work state."""
    states, _ = group_work(events)
    assert len(states) == 1
    return states[0]


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
    key = keyed("k")
    unkeyed = make_event("u")

    states, independents = group_work([key, unkeyed])

    assert [state.key for state in states] == [("tasks", "task", "M-1")]
    assert [event.id for event in independents] == ["u"]


def test_is_informational_only_when_no_status_and_no_deadline() -> None:
    assert is_informational(make_event(status=None, due_at=None)) is True
    assert is_informational(make_event(status="blocked")) is False
    assert is_informational(make_event(due_at=NOW)) is False


def test_current_status_is_the_latest_stated_status() -> None:
    first = keyed("a", status="open", occurred_at=NOW - timedelta(hours=3))
    second = keyed("b", status="blocked", occurred_at=NOW - timedelta(hours=1))

    state = only_state([second, first])

    assert state.status is EventStatus.BLOCKED
    assert state.status_event is not None and state.status_event.id == "b"
    assert [event.id for event in state.events] == ["a", "b"]


def test_equal_occurrence_breaks_ties_by_receipt_then_id() -> None:
    occurred = NOW - timedelta(hours=2)
    early_receipt = keyed(
        "b", status="open", occurred_at=occurred, received_at=NOW - timedelta(minutes=30)
    )
    late_receipt = keyed(
        "a", status="blocked", occurred_at=occurred, received_at=NOW - timedelta(minutes=10)
    )

    state = only_state([early_receipt, late_receipt])

    # 'a' is received later, so it orders last and its status is current.
    assert state.status is EventStatus.BLOCKED
    assert state.status_event is not None and state.status_event.id == "a"


def test_a_late_arriving_earlier_event_is_not_the_current_state() -> None:
    newer = keyed(
        "new",
        status="blocked",
        occurred_at=NOW - timedelta(hours=1),
        received_at=NOW - timedelta(hours=1),
    )
    stale = keyed(
        "old",
        status="open",
        occurred_at=NOW - timedelta(hours=5),
        received_at=NOW,
    )

    state = only_state([newer, stale])

    assert state.status is EventStatus.BLOCKED
    assert state.status_event is not None and state.status_event.id == "new"


def test_is_cleared_reflects_the_current_status() -> None:
    blocked = keyed("a", status="blocked", occurred_at=NOW - timedelta(hours=3))
    resolved = keyed("b", status="resolved", occurred_at=NOW - timedelta(hours=1))

    cleared = only_state([blocked, resolved])
    active = only_state([blocked])

    assert cleared.is_cleared is True
    assert active.is_cleared is False


def test_an_informational_event_preserves_the_known_status() -> None:
    # A progress comment carrying no status must not clear a blocked task.
    blocked = keyed("a", status="blocked", occurred_at=NOW - timedelta(hours=3))
    comment = keyed("b", occurred_at=NOW - timedelta(hours=1))

    state = only_state([blocked, comment])

    assert state.status is EventStatus.BLOCKED
    # The event that established the current status is the blocked report, not the note.
    assert state.status_event is not None and state.status_event.id == "a"
    assert state.is_cleared is False


def test_a_later_deadline_replaces_the_earlier_one() -> None:
    first = keyed(
        "a", status="open", due_at=NOW - timedelta(hours=2), occurred_at=NOW - timedelta(hours=3)
    )
    rescheduled = keyed(
        "b", status="open", due_at=NOW + timedelta(days=1), occurred_at=NOW - timedelta(hours=1)
    )

    state = only_state([first, rescheduled])

    assert state.due_at == NOW + timedelta(days=1)
    assert state.due_event is not None and state.due_event.id == "b"
    assert state.overdue_deadline(NOW) is None


def test_an_omitted_deadline_leaves_the_prior_one_standing() -> None:
    due = NOW - timedelta(hours=2)
    dated = keyed("a", status="open", due_at=due, occurred_at=NOW - timedelta(hours=3))
    update = keyed("b", status="in_progress", occurred_at=NOW - timedelta(hours=1))

    state = only_state([dated, update])

    # The update did not mention a deadline, so the prior one still applies.
    assert state.due_at == due
    assert state.due_event is not None and state.due_event.id == "a"
    deadline = state.overdue_deadline(NOW)
    assert deadline is not None and deadline.id == "a"


def test_a_terminal_status_clears_the_deadline() -> None:
    due = NOW - timedelta(hours=2)
    dated = keyed("a", status="overdue", due_at=due, occurred_at=NOW - timedelta(hours=3))
    resolved = keyed("b", status="resolved", occurred_at=NOW - timedelta(hours=1))

    state = only_state([dated, resolved])

    assert state.due_at is None
    assert state.due_event is None
    assert state.overdue_deadline(NOW) is None


def test_overdue_deadline_is_none_before_the_deadline_passes() -> None:
    dated = keyed(
        "a", status="open", due_at=NOW + timedelta(hours=1), occurred_at=NOW - timedelta(hours=1)
    )

    state = only_state([dated])

    assert state.overdue_deadline(NOW) is None


def test_blocked_since_is_the_start_of_the_current_block() -> None:
    open_event = keyed("a", status="open", occurred_at=NOW - timedelta(hours=5))
    first_block = keyed("b", status="blocked", occurred_at=NOW - timedelta(hours=4))
    still_block = keyed("c", status="blocked", occurred_at=NOW - timedelta(hours=1))

    state = only_state([open_event, first_block, still_block])

    assert state.blocked_since is not None
    assert state.blocked_since.id == "b"


def test_blocked_since_survives_an_informational_event_in_the_run() -> None:
    # An informational note during a block must not restart the blocked clock.
    first_block = keyed("b", status="blocked", occurred_at=NOW - timedelta(hours=4))
    comment = keyed("c", occurred_at=NOW - timedelta(hours=2))
    still_block = keyed("d", status="blocked", occurred_at=NOW - timedelta(hours=1))

    state = only_state([first_block, comment, still_block])

    assert state.blocked_since is not None
    assert state.blocked_since.id == "b"


def test_blocked_since_is_none_when_current_is_not_blocked() -> None:
    blocked = keyed("a", status="blocked", occurred_at=NOW - timedelta(hours=3))
    running = keyed("b", status="in_progress", occurred_at=NOW - timedelta(hours=1))

    state = only_state([blocked, running])

    assert state.blocked_since is None


def test_a_reblock_after_clearing_starts_a_new_run() -> None:
    first_block = keyed("a", status="blocked", occurred_at=NOW - timedelta(hours=5))
    resolved = keyed("b", status="resolved", occurred_at=NOW - timedelta(hours=3))
    reblock = keyed("c", status="blocked", occurred_at=NOW - timedelta(hours=1))

    state = only_state([first_block, resolved, reblock])

    assert state.blocked_since is not None
    assert state.blocked_since.id == "c"


def test_states_are_ordered_by_key() -> None:
    a = make_event("a", entity_type="task", entity_id="M-2")
    b = make_event("b", entity_type="task", entity_id="M-1")

    states, _ = group_work([a, b])

    assert [state.key for state in states] == [
        ("tasks", "task", "M-1"),
        ("tasks", "task", "M-2"),
    ]


def test_an_entity_of_only_informational_events_has_no_current_state() -> None:
    state = only_state([keyed("a"), keyed("b")])

    assert state.status is None
    assert state.status_event is None
    assert state.due_at is None
    assert state.blocked_since is None
    assert state.is_cleared is False
