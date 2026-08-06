"""Recognising operational work that is blocked.

Work is blocked when its producer has reported it as such: something is standing
in the way and the work is not progressing under its own power. Unlike overdue
work, blocked work needs no deadline to be a concern — a task that cannot move is
a risk whether or not a clock is running on it.

The rule reads the status a producer stated rather than inferring one, so the
judgement is theirs to make. How long the work has been blocked is judged against
a reference instant rather than the wall clock, so the same events and the same
instant always classify the same way. That keeps detection deterministic and lets
a test pin the escalation boundary exactly.
"""

from opsbrief.events import Event, EventStatus


def is_blocked_work(event: Event) -> bool:
    """Return whether ``event`` describes work its producer reported as blocked.

    Blocked is a state a producer states explicitly, so the rule trusts it rather
    than guessing: an event counts when, and only when, its ``status`` is
    ``blocked``. An event with any other status, or none at all, is not blocked
    work as far as this rule is concerned.
    """
    return event.status == EventStatus.BLOCKED
