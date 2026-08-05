"""Concrete risk rules that implement the :class:`~opsbrief.risks.RiskRule` protocol."""

from opsbrief.risks.rules.overdue import is_overdue_work

__all__ = ["is_overdue_work"]
