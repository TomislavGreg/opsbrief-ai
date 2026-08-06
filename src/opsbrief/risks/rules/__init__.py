"""Concrete risk rules that implement the :class:`~opsbrief.risks.RiskRule` protocol."""

from opsbrief.risks.rules.blocked import BlockedWorkRule, is_blocked_work
from opsbrief.risks.rules.integration import (
    RepeatedIntegrationFailureRule,
    is_integration_failure,
    is_integration_recovery,
)
from opsbrief.risks.rules.overdue import OverdueWorkRule, is_overdue_work

__all__ = [
    "BlockedWorkRule",
    "OverdueWorkRule",
    "RepeatedIntegrationFailureRule",
    "is_blocked_work",
    "is_integration_failure",
    "is_integration_recovery",
    "is_overdue_work",
]
