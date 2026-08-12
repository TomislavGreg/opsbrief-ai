"""Tests for the incident status lifecycle."""

from opsbrief.incidents import (
    ACTIVE_STATUSES,
    ALLOWED_TRANSITIONS,
    INACTIVE_STATUSES,
    TERMINAL_STATUSES,
    IncidentStatus,
    InvalidIncidentTransition,
    can_transition,
)


def test_the_five_states_are_named() -> None:
    assert {status.value for status in IncidentStatus} == {
        "open",
        "investigating",
        "monitoring",
        "resolved",
        "closed",
    }


def test_active_and_inactive_states_partition_the_lifecycle() -> None:
    # Every state is either active or inactive, and none is both.
    every_state = set(IncidentStatus)
    assert every_state == ACTIVE_STATUSES | INACTIVE_STATUSES
    assert not (ACTIVE_STATUSES & INACTIVE_STATUSES)


def test_closed_is_the_only_terminal_state() -> None:
    assert set(TERMINAL_STATUSES) == {IncidentStatus.CLOSED}
    assert not ALLOWED_TRANSITIONS[IncidentStatus.CLOSED]


def test_every_state_has_a_transition_entry() -> None:
    # No state may be missing from the map, or can_transition would raise on it.
    assert set(ALLOWED_TRANSITIONS) == set(IncidentStatus)


def test_a_state_never_transitions_to_itself() -> None:
    for status, targets in ALLOWED_TRANSITIONS.items():
        assert status not in targets


def test_an_open_incident_can_move_to_any_later_state() -> None:
    assert can_transition(IncidentStatus.OPEN, IncidentStatus.INVESTIGATING)
    assert can_transition(IncidentStatus.OPEN, IncidentStatus.RESOLVED)
    assert can_transition(IncidentStatus.OPEN, IncidentStatus.CLOSED)


def test_a_resolved_incident_can_reopen_or_close() -> None:
    assert can_transition(IncidentStatus.RESOLVED, IncidentStatus.INVESTIGATING)
    assert can_transition(IncidentStatus.RESOLVED, IncidentStatus.CLOSED)


def test_a_resolved_incident_cannot_jump_back_to_open() -> None:
    # Reopening means resuming investigation, not pretending it is untouched.
    assert not can_transition(IncidentStatus.RESOLVED, IncidentStatus.OPEN)


def test_a_closed_incident_moves_nowhere() -> None:
    for status in IncidentStatus:
        assert not can_transition(IncidentStatus.CLOSED, status)


def test_the_same_state_is_never_a_transition() -> None:
    for status in IncidentStatus:
        assert not can_transition(status, status)


def test_invalid_transition_error_carries_the_states() -> None:
    error = InvalidIncidentTransition(IncidentStatus.CLOSED, IncidentStatus.OPEN)

    assert error.current is IncidentStatus.CLOSED
    assert error.target is IncidentStatus.OPEN
    assert "closed" in str(error)
    assert "open" in str(error)
    assert isinstance(error, ValueError)
