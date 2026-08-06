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

from collections.abc import Sequence
from datetime import datetime, timedelta

from opsbrief.events import Event, EventStatus, as_utc
from opsbrief.risks.schema import Risk, RiskSeverity

#: Identifier the blocked-work rule tags its risks with.
RULE_ID = "blocked_work"

#: Once work has been blocked this long the risk escalates from medium to high.
ESCALATION_AFTER = timedelta(hours=24)

#: Fixed UTC rendering of a timestamp for the human-readable explanation.
_DISPLAY_FORMAT = "%Y-%m-%d %H:%M UTC"


def is_blocked_work(event: Event) -> bool:
    """Return whether ``event`` describes work its producer reported as blocked.

    Blocked is a state a producer states explicitly, so the rule trusts it rather
    than guessing: an event counts when, and only when, its ``status`` is
    ``blocked``. An event with any other status, or none at all, is not blocked
    work as far as this rule is concerned.
    """
    return event.status == EventStatus.BLOCKED


def _shorten(text: str, limit: int) -> str:
    """Return ``text`` unchanged, or truncated with an ellipsis to fit ``limit``."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class BlockedWorkRule:
    """Raise a risk for every event describing work reported as blocked.

    The rule is built with the reference instant it judges against, so two runs
    over the same events at the same instant raise equal risks. Blocked work is a
    risk with or without a deadline; how long it has been blocked, measured from
    when the event was reported, decides how urgent it is. A risk is medium until
    the work has been blocked for at least :data:`ESCALATION_AFTER`, when it
    escalates to high; ranking risks against each other is left to priority
    scoring.

    Each risk cites the single event behind it, and the risks are returned
    longest-blocked first, ties broken by event id, so the ordering is stable.
    """

    rule_id = RULE_ID

    def __init__(self, now: datetime) -> None:
        self._now = as_utc(now)

    def evaluate(self, events: Sequence[Event]) -> list[Risk]:
        """Return one risk per blocked event, longest blocked first."""
        blocked = [event for event in events if is_blocked_work(event)]
        blocked.sort(key=lambda event: (event.occurred_at, event.id))
        return [self._risk(event) for event in blocked]

    def _risk(self, event: Event) -> Risk:
        """Build the risk for one blocked event, tagged and traceable."""
        blocked_since = event.occurred_at.strftime(_DISPLAY_FORMAT)
        now = self._now.strftime(_DISPLAY_FORMAT)
        return Risk(
            rule=self.rule_id,
            title=_shorten(f"{event.subject} is blocked", 200),
            detail=(
                f'Work "{event.subject}" was reported blocked at {blocked_since} and '
                f"has not progressed. It is still blocked as of {now}."
            ),
            severity=self._severity(event.occurred_at),
            event_ids=[event.id],
        )

    def _severity(self, occurred_at: datetime) -> RiskSeverity:
        """Return the risk severity for work blocked since ``occurred_at``.

        Work escalates to high once it has been blocked for at least
        :data:`ESCALATION_AFTER`; exactly at that boundary it is already high.
        Work reported blocked at a moment still in the future stays medium.
        """
        blocked_for = self._now - occurred_at
        return RiskSeverity.HIGH if blocked_for >= ESCALATION_AFTER else RiskSeverity.MEDIUM
