"""The incident status lifecycle.

An incident moves through a small set of states, and not every move between
them is meaningful. A closed incident does not reopen itself; a monitoring
incident that recurs goes back to investigation rather than straight to open.
Encoding the allowed moves here — deterministically, in one place — keeps the
lifecycle explainable and stops the rest of the codebase from inventing states
or transitions of its own.

The states divide into two groups. An incident is *active* while it is still
being worked (``open``, ``investigating``, ``monitoring``) and *inactive* once
it has stopped (``resolved``, ``closed``). ``closed`` is terminal: it is the
one state with no move out of it.
"""

from enum import StrEnum


class IncidentStatus(StrEnum):
    """Where an incident sits in its lifecycle.

    ``open`` is a freshly declared incident nobody has picked up yet;
    ``investigating`` is one being actively worked; ``monitoring`` is one whose
    mitigation is in place and is being watched for recurrence; ``resolved`` is
    one believed fixed; and ``closed`` is one signed off, the terminal state.
    """

    OPEN = "open"
    INVESTIGATING = "investigating"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    CLOSED = "closed"


#: States in which an incident is still being worked. An active incident has no
#: resolution instant, because it has not stopped.
ACTIVE_STATUSES: frozenset[IncidentStatus] = frozenset(
    {IncidentStatus.OPEN, IncidentStatus.INVESTIGATING, IncidentStatus.MONITORING}
)

#: States in which an incident has stopped being active. An inactive incident
#: carries the instant it stopped, so a reader knows when it ended.
INACTIVE_STATUSES: frozenset[IncidentStatus] = frozenset(
    {IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
)

#: The one state with no move out of it: a closed incident stays closed.
TERMINAL_STATUSES: frozenset[IncidentStatus] = frozenset({IncidentStatus.CLOSED})

#: The moves allowed out of each state. A transition to the same state is not a
#: move and is not listed. A resolved incident may be reopened for investigation
#: if it recurs, or closed once signed off; a closed incident moves nowhere.
ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.OPEN: frozenset(
        {
            IncidentStatus.INVESTIGATING,
            IncidentStatus.MONITORING,
            IncidentStatus.RESOLVED,
            IncidentStatus.CLOSED,
        }
    ),
    IncidentStatus.INVESTIGATING: frozenset(
        {IncidentStatus.MONITORING, IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
    ),
    IncidentStatus.MONITORING: frozenset(
        {IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
    ),
    IncidentStatus.RESOLVED: frozenset({IncidentStatus.INVESTIGATING, IncidentStatus.CLOSED}),
    IncidentStatus.CLOSED: frozenset(),
}


class InvalidIncidentTransition(ValueError):
    """Raised when a status change is not allowed by the lifecycle.

    It is a ``ValueError`` so that a caller can treat it as ordinary invalid
    input, but it carries the ``current`` and ``target`` states so the reason is
    never a mystery.
    """

    def __init__(self, current: IncidentStatus, target: IncidentStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"an incident cannot move from {current.value!r} to {target.value!r}")


def can_transition(current: IncidentStatus, target: IncidentStatus) -> bool:
    """Return whether the lifecycle allows moving from ``current`` to ``target``.

    A move to the same state is never a transition, so it is not allowed here;
    callers that treat re-applying a status as a no-op should check for equality
    themselves before asking.
    """
    return target in ALLOWED_TRANSITIONS[current]
