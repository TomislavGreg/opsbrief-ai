"""Ranking risks from different rules against each other.

Each rule decides how urgent its own risks are, expressed as a
:class:`~opsbrief.risks.schema.RiskSeverity`. That is enough to order one rule's
output, but a duty manager reads every rule's risks in one list and needs the
most pressing at the top regardless of which rule raised it. This module is that
cross-rule ordering.

Priority is deterministic and rule-based, exactly like detection: no language
model has a say. Severity is the dominant signal — a critical risk always
outranks a high one, whatever else is true — and the amount of evidence breaks
ties, on the view that a concern backed by more events is the more pressing of
two otherwise equal ones. Anything still tied is ordered by rule, then title,
then first source event id, so the result is a total order that never depends on
the order the risks arrived in.
"""

from collections.abc import Sequence

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


def _priority_key(risk: Risk) -> tuple[int, int, str, str, str]:
    """Return the sort key that orders ``risk`` against others, most urgent first.

    The numeric terms are negated so a plain ascending sort puts the highest
    score and the most evidence first, while the trailing identifiers stay in
    natural ascending order for a stable, readable tie-break.
    """
    return (
        -priority_score(risk),
        -len(risk.event_ids),
        risk.rule,
        risk.title,
        risk.event_ids[0],
    )


def prioritize(risks: Sequence[Risk]) -> list[Risk]:
    """Return ``risks`` in a new list ordered most urgent first.

    Ordering is by :func:`priority_score` first, then by how many source events
    back the risk, then by rule, title and first event id. The order is total and
    deterministic: the same risks always come back the same way, whatever order
    they were given in, and the input sequence is left untouched.
    """
    return sorted(risks, key=_priority_key)
