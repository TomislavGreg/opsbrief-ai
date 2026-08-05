"""The risk-rule interface and the detector that runs rules.

A rule is the unit of risk detection: it reads a batch of stored events and
returns the risks it recognises, each tagged with the rule's identifier and the
events behind it. Rules are deterministic and independent — the same events
always yield the same risks, and no rule depends on another — so the detector
can run them in any order and simply collect what they raise.

This module defines the contract, not the rules themselves. Concrete rules for
overdue work, blocked work and repeated integration failures implement
:class:`RiskRule` and are added in their own tickets.
"""

from collections.abc import Iterable, Sequence
from typing import Protocol, runtime_checkable

from opsbrief.events import Event
from opsbrief.risks.schema import Risk


@runtime_checkable
class RiskRule(Protocol):
    """A deterministic rule that raises risks from stored events.

    A rule carries a stable :attr:`rule_id` and tags every risk it raises with
    it, so a risk can always be traced back to the rule that decided it. A rule
    never consults a language model and never mutates the events it is given:
    evaluating the same events twice returns equal risks both times.
    """

    #: Stable identifier the rule tags its risks with, for example 'overdue_work'.
    rule_id: str

    def evaluate(self, events: Sequence[Event]) -> list[Risk]:
        """Return the risks this rule recognises in ``events``.

        The result is empty when the rule finds nothing. Each returned risk
        cites the events behind it by ``id``, so the caller can trace it.
        """
        ...


def detect_risks(events: Sequence[Event], rules: Iterable[RiskRule]) -> list[Risk]:
    """Run every rule over ``events`` and collect the risks they raise.

    Rules are independent, so the risks are simply gathered rule by rule, in the
    order the rules are given: a rule that raises nothing contributes nothing,
    and no rule sees another's output. Ordering the result by urgency is a
    separate concern handled when risks are scored, not here.

    The events are passed through untouched, so a caller may share one sequence
    across every rule.
    """
    risks: list[Risk] = []
    for rule in rules:
        risks.extend(rule.evaluate(events))
    return risks
