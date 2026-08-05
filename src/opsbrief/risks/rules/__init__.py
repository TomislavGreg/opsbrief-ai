"""Concrete risk rules that implement the :class:`~opsbrief.risks.RiskRule` protocol."""

from opsbrief.risks.rules.overdue import OverdueWorkRule, is_overdue_work

__all__ = ["OverdueWorkRule", "is_overdue_work"]
