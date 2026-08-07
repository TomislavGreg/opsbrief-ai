"""Ranking risks from different rules against each other.

Each rule decides how urgent its own risks are, expressed as a
:class:`~opsbrief.risks.schema.RiskSeverity`. That is enough to order one rule's
output, but a duty manager reads every rule's risks in one list and needs the
most pressing at the top regardless of which rule raised it. This module is that
cross-rule ordering.

Priority is deterministic and rule-based, exactly like detection: no language
model has a say. Severity is the dominant signal — a critical risk always
outranks a high one, whatever else is true — expressed here as a numeric weight
so risks from different rules become directly comparable.
"""

from opsbrief.risks.schema import Risk, RiskSeverity

#: How much each severity weighs when ranking risks. Higher is more urgent, and
#: the steps are what a lower severity can never make up on evidence alone.
SEVERITY_WEIGHT: dict[RiskSeverity, int] = {
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.CRITICAL: 4,
}


def priority_score(risk: Risk) -> int:
    """Return the coarse priority of ``risk``: its severity weight, 1 to 4.

    This is the dominant term in any ordering and the number worth surfacing to a
    reader. It is deliberately coarse — two risks of the same severity share a
    score — because finer separation is a tie-break, not a claim that one high
    risk is truly more urgent than another. Higher means more pressing.
    """
    return SEVERITY_WEIGHT[risk.severity]
