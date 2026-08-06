"""Recognising an integration that keeps failing.

A single integration failure is noise; the same integration failing again and
again is a risk. This rule groups failure events by the integration they concern
and raises a risk once one integration has failed enough times inside a recent
window, without recovering since.

Which events count is decided from the schema the producer already fills in. A
failure is an event whose ``status`` is ``failed``; a recovery is one whose
``status`` is ``resolved``. Both must name the integration they are about through
``entity_id`` — the rule cannot say "the same integration failed repeatedly"
without an identifier to group by, so failures that name no entity are left to
other rules. A recovery that lands after a run of failures clears them, the same
way a resolved status clears overdue work: the manager is shown integrations that
are failing now, not ones that already came back.

The window and the recovery comparison are judged against a reference instant
rather than the wall clock, so the same events and the same instant always
classify the same way, and a test can pin the boundary exactly.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from opsbrief.events import Event, EventStatus, as_utc
from opsbrief.risks.schema import Risk, RiskSeverity

#: An integration's grouping key: the producer, the kind of thing, and its id.
IntegrationKey = tuple[str, str | None, str]

#: Identifier the repeated-failure rule tags its risks with.
RULE_ID = "repeated_integration_failure"

#: How many unrecovered failures inside the window it takes to raise a risk.
FAILURE_THRESHOLD = 3

#: At or above this many failures the risk is critical rather than high.
ESCALATION_COUNT = 5

#: Only failures this recent count, so a burst long since past does not linger.
WINDOW = timedelta(days=7)

#: Fixed UTC rendering of a timestamp for the human-readable explanation.
_DISPLAY_FORMAT = "%Y-%m-%d %H:%M UTC"


def is_integration_failure(event: Event) -> bool:
    """Return whether ``event`` reports an identifiable integration failure.

    An event counts when its ``status`` is ``failed`` and it names the
    integration it concerns through ``entity_id``. A failure that names no entity
    cannot be attributed to a specific integration, so this rule leaves it alone.
    """
    return event.status == EventStatus.FAILED and event.entity_id is not None


def is_integration_recovery(event: Event) -> bool:
    """Return whether ``event`` reports an identifiable integration recovery.

    An event counts when its ``status`` is ``resolved`` and it names the
    integration it concerns through ``entity_id``, so a recovery can be matched to
    the failures it clears.
    """
    return event.status == EventStatus.RESOLVED and event.entity_id is not None


def integration_key(event: Event) -> IntegrationKey:
    """Return the key identifying the integration ``event`` is about.

    Events sharing a key are treated as the same integration: the same producing
    ``source``, ``entity_type`` and ``entity_id``. The caller is expected to have
    checked that ``entity_id`` is present, which every failure and recovery this
    rule considers has.
    """
    assert event.entity_id is not None  # guaranteed by the failure/recovery checks
    return (event.source, event.entity_type, event.entity_id)


def _shorten(text: str, limit: int) -> str:
    """Return ``text`` unchanged, or truncated with an ellipsis to fit ``limit``."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


class RepeatedIntegrationFailureRule:
    """Raise a risk for every integration failing repeatedly and not yet recovered.

    The rule is built with the reference instant it judges against, so two runs
    over the same events at the same instant raise equal risks. It groups failures
    by the integration they name, keeps only those inside :data:`WINDOW` before the
    instant and after the integration's most recent recovery, and raises a risk
    once a group holds at least :data:`FAILURE_THRESHOLD` of them. A recovery lands
    after a run of failures clears it, so an integration that came back raises
    nothing.

    Each risk cites every failure behind it, oldest first, so the whole run is
    traceable. Severity is high, rising to critical once a group reaches
    :data:`ESCALATION_COUNT` failures. Risks are returned most-failures first, ties
    broken by the first cited event id, so the ordering is stable.
    """

    rule_id = RULE_ID

    def __init__(self, now: datetime) -> None:
        self._now = as_utc(now)
        self._since = self._now - WINDOW

    def evaluate(self, events: Sequence[Event]) -> list[Risk]:
        """Return one risk per integration failing repeatedly, most failures first."""
        failures: dict[IntegrationKey, list[Event]] = {}
        recoveries: dict[IntegrationKey, list[Event]] = {}
        for event in events:
            if is_integration_failure(event):
                failures.setdefault(integration_key(event), []).append(event)
            elif is_integration_recovery(event):
                recoveries.setdefault(integration_key(event), []).append(event)

        risks: list[Risk] = []
        for key, group in failures.items():
            active = self._active_failures(group, recoveries.get(key, []))
            if len(active) >= FAILURE_THRESHOLD:
                risks.append(self._risk(active))

        risks.sort(key=lambda risk: (-len(risk.event_ids), risk.event_ids[0]))
        return risks

    def _active_failures(self, failures: list[Event], recoveries: list[Event]) -> list[Event]:
        """Return the in-window failures not cleared by a later recovery, oldest first.

        A failure counts when it occurred within :data:`WINDOW` before the
        reference instant and strictly after the integration's most recent
        recovery; a recovery exactly at a failure's instant does not clear it.
        """
        last_recovery = max((event.occurred_at for event in recoveries), default=None)
        active = [
            event
            for event in failures
            if self._since <= event.occurred_at <= self._now
            and (last_recovery is None or event.occurred_at > last_recovery)
        ]
        active.sort(key=lambda event: (event.occurred_at, event.id))
        return active

    def _risk(self, failures: list[Event]) -> Risk:
        """Build the risk for one integration's run of failures, tagged and traceable."""
        first = failures[0]
        count = len(failures)
        entity_id = first.entity_id
        kind = first.entity_type or "integration"
        earliest = failures[0].occurred_at.strftime(_DISPLAY_FORMAT)
        latest = failures[-1].occurred_at.strftime(_DISPLAY_FORMAT)
        now = self._now.strftime(_DISPLAY_FORMAT)
        return Risk(
            rule=self.rule_id,
            title=_shorten(f"Integration {entity_id} has failed {count} times", 200),
            detail=(
                f'{kind.capitalize()} "{entity_id}" (source: {first.source}) has failed '
                f"{count} times between {earliest} and {latest} with no recovery since. "
                f"It is a repeated failure as of {now}."
            ),
            severity=self._severity(count),
            event_ids=[event.id for event in failures],
        )

    def _severity(self, count: int) -> RiskSeverity:
        """Return the severity for ``count`` unrecovered failures.

        A repeated failure is high from the threshold up, rising to critical once
        the run reaches :data:`ESCALATION_COUNT`.
        """
        return RiskSeverity.CRITICAL if count >= ESCALATION_COUNT else RiskSeverity.HIGH
