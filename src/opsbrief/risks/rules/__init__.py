"""Concrete risk rules that implement the :class:`~opsbrief.risks.RiskRule` protocol."""

from opsbrief.risks.rules.blocked import BlockedWorkRule, is_blocked_work
from opsbrief.risks.rules.overdue import OverdueWorkRule, is_overdue_work

__all__ = ["BlockedWorkRule", "OverdueWorkRule", "is_blocked_work", "is_overdue_work"]
