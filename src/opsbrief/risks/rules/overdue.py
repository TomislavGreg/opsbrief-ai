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

from collections.abc import Sequence
from datetime import datetime, timedelta

from opsbrief.events import Event, EventStatus, as_utc
from opsbrief.risks.schema import Risk, RiskSeverity

#: States in which a deadline no longer matters, so passing it raises no risk.
TERMINAL_STATUSES = frozenset({EventStatus.RESOLVED, EventStatus.CANCELLED})

#: Identifier the overdue rule tags its risks with.
RULE_ID = "overdue_work"

#: Once work is this far past its deadline the risk escalates from medium to high.
ESCALATION_AFTER = timedelta(hours=24)

#: Fixed UTC rendering of a timestamp for the human-readable explanation.
_DISPLAY_FORMAT = "%Y-%m-%d %H:%M UTC"


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


def _shorten(text: str, limit: int) -> str:
    """Return ``text`` unchanged, or truncated with an ellipsis to fit ``limit``."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class OverdueWorkRule:
    """Raise a risk for every event describing work past its deadline.

    The rule is built with the reference instant it judges against, so two runs
    over the same events at the same instant raise equal risks. A risk escalates
    from medium to high once the work is at least :data:`ESCALATION_AFTER` past
    its deadline; ranking risks against each other is left to priority scoring.

    Each risk cites the single event behind it, and the risks are returned
    most-overdue first, ties broken by event id, so the ordering is stable.
    """

    rule_id = RULE_ID

    def __init__(self, now: datetime) -> None:
        self._now = as_utc(now)

    def evaluate(self, events: Sequence[Event]) -> list[Risk]:
        """Return one risk per overdue event, most overdue first."""
        overdue = [event for event in events if is_overdue_work(event, self._now)]
        overdue.sort(key=lambda event: (event.due_at, event.id))
        return [self._risk(event) for event in overdue]

    def _risk(self, event: Event) -> Risk:
        """Build the risk for one overdue event, tagged and traceable."""
        assert event.due_at is not None  # guaranteed by is_overdue_work
        due = event.due_at.strftime(_DISPLAY_FORMAT)
        now = self._now.strftime(_DISPLAY_FORMAT)
        status_clause = f" (status: {event.status.value})" if event.status is not None else ""
        return Risk(
            rule=self.rule_id,
            title=_shorten(f"{event.subject} is overdue", 200),
            detail=(
                f'Work "{event.subject}" was due at {due} and has not been resolved'
                f"{status_clause}. It is overdue as of {now}."
            ),
            severity=self._severity(event.due_at),
            event_ids=[event.id],
        )

    def _severity(self, due_at: datetime) -> RiskSeverity:
        """Return the risk severity for work due at ``due_at``.

        Work escalates to high once it is at least :data:`ESCALATION_AFTER` late;
        exactly at that boundary it is already high.
        """
        lateness = self._now - due_at
        return RiskSeverity.HIGH if lateness >= ESCALATION_AFTER else RiskSeverity.MEDIUM
