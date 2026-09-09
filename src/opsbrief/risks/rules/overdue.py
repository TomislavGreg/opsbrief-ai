"""Recognising operational work that has missed its deadline.

Work is overdue when it carried a deadline, that deadline has passed, and the
work is not yet finished. "Finished" means resolved or cancelled: those are the
states in which a deadline no longer matters. Anything else with a past
``due_at`` — open, in progress, blocked, failed, already flagged overdue by its
producer — still counts, because the work it describes was not done in time.

A producer reports the same work more than once as its state changes. Events that
name a stable entity (a source with an ``entity_type`` and ``entity_id``) are
grouped, and only the entity's current state, its most recent event, is judged:
a later resolved or cancelled event clears the earlier deadline, and a later
deadline replaces an earlier one, so work that has since been finished or
rescheduled stops being reported. Events that name no entity cannot be correlated
across reports, so each is judged on its own. The whole history stays stored as
evidence either way. See :mod:`opsbrief.risks.work_state`.

The judgement is made against a reference instant rather than the wall clock, so
the same events and the same instant always classify the same way. That keeps
detection deterministic and lets a test pin the boundary exactly.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from opsbrief.events import Event, EventStatus, as_utc
from opsbrief.risks.schema import Risk, RiskSeverity
from opsbrief.risks.work_state import TERMINAL_STATUSES, group_work, occurred_by

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


@dataclass(frozen=True)
class _OverdueItem:
    """One overdue work item, drawn from a projected state or a lone event.

    Keeping the fields a risk is built from together lets the keyed and unkeyed
    paths share one ordering and one risk builder. ``status`` is the current
    status the deadline is judged against, and ``event_id`` cites the event that
    set the deadline.
    """

    subject: str
    due_at: datetime
    status: EventStatus | None
    event_id: str


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
        """Return one risk per overdue work item, most overdue first.

        Each tracked entity contributes at most one risk, judged on its projected
        current state, so a piece of work that was resolved or rescheduled no
        longer shows as overdue and repeated or informational reports of the same
        work do not each raise a risk. The event cited is the one that set the
        current deadline. Events that name no entity are judged individually, as
        before. Events occurring after the reference instant are future reports and
        take no part in the present snapshot.
        """
        states, unkeyed = group_work(occurred_by(events, self._now))
        overdue: list[_OverdueItem] = []
        for state in states:
            deadline = state.overdue_deadline(self._now)
            if deadline is not None:
                overdue.append(
                    _OverdueItem(
                        subject=deadline.subject,
                        due_at=deadline.due_at,
                        status=state.status,
                        event_id=deadline.id,
                    )
                )
        overdue += [
            _OverdueItem(
                subject=event.subject,
                due_at=event.due_at,
                status=event.status,
                event_id=event.id,
            )
            for event in unkeyed
            if is_overdue_work(event, self._now)
        ]
        overdue.sort(key=lambda item: (item.due_at, item.event_id))
        return [self._risk(item) for item in overdue]

    def _risk(self, item: _OverdueItem) -> Risk:
        """Build the risk for one overdue work item, tagged and traceable."""
        due = item.due_at.strftime(_DISPLAY_FORMAT)
        now = self._now.strftime(_DISPLAY_FORMAT)
        status_clause = f" (status: {item.status.value})" if item.status is not None else ""
        return Risk(
            rule=self.rule_id,
            title=_shorten(f"{item.subject} is overdue", 200),
            detail=(
                f'Work "{item.subject}" was due at {due} and has not been resolved'
                f"{status_clause}. It is overdue as of {now}."
            ),
            severity=self._severity(item.due_at),
            event_ids=[item.event_id],
        )

    def _severity(self, due_at: datetime) -> RiskSeverity:
        """Return the risk severity for work due at ``due_at``.

        Work escalates to high once it is at least :data:`ESCALATION_AFTER` late;
        exactly at that boundary it is already high.
        """
        lateness = self._now - due_at
        return RiskSeverity.HIGH if lateness >= ESCALATION_AFTER else RiskSeverity.MEDIUM
