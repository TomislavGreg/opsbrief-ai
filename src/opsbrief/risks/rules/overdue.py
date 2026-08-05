"""Recognising operational work that has missed its deadline.

Work is overdue when it carried a deadline, that deadline has passed, and the
work is not yet finished. "Finished" means resolved or cancelled: those are the
states in which a deadline no longer matters. Anything else with a past
``due_at`` — open, in progress, blocked, failed, already flagged overdue by its
producer — still counts, because the work it describes was not done in time.

The judgement is made against a reference instant rather than the wall clock, so
the same events and the same instant always classify the same way. That keeps
detection deterministic and lets a test pin the boundary exactly.
"""

from datetime import datetime

from opsbrief.events import Event, EventStatus, as_utc

#: States in which a deadline no longer matters, so passing it raises no risk.
TERMINAL_STATUSES = frozenset({EventStatus.RESOLVED, EventStatus.CANCELLED})


def is_overdue_work(event: Event, now: datetime) -> bool:
    """Return whether ``event`` describes work overdue at ``now``.

    An event is overdue when it has a ``due_at`` strictly before ``now`` and is
    not in a terminal state. An event with no deadline is never overdue, and one
    that is exactly at its deadline is not yet overdue: the deadline has to have
    passed. ``now`` is read in UTC, matching the UTC ``due_at`` on stored events.
    """
    if event.due_at is None:
        return False
    if event.status in TERMINAL_STATUSES:
        return False
    return event.due_at < as_utc(now)
