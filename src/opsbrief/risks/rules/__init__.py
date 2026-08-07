"""Concrete risk rules that implement the :class:`~opsbrief.risks.RiskRule` protocol."""

from collections.abc import Sequence
from datetime import datetime

from opsbrief.risks.engine import RiskRule
from opsbrief.risks.rules.blocked import BlockedWorkRule, is_blocked_work
from opsbrief.risks.rules.integration import (
    RepeatedIntegrationFailureRule,
    is_integration_failure,
    is_integration_recovery,
)
from opsbrief.risks.rules.overdue import OverdueWorkRule, is_overdue_work


def default_rules(now: datetime) -> Sequence[RiskRule]:
    """Return every implemented risk rule, each judging against ``now``.

    This is the canonical rule set the service and any future caller run so that
    a risk snapshot reflects all detection the product implements, not a subset
    someone remembered to list. All rules share the one reference instant, so the
    whole snapshot is judged at a single moment.
    """
    return [
        OverdueWorkRule(now),
        BlockedWorkRule(now),
        RepeatedIntegrationFailureRule(now),
    ]


__all__ = [
    "BlockedWorkRule",
    "OverdueWorkRule",
    "RepeatedIntegrationFailureRule",
    "default_rules",
    "is_blocked_work",
    "is_integration_failure",
    "is_integration_recovery",
    "is_overdue_work",
]
