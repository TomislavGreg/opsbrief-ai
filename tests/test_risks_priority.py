"""Tests for risk priority scoring."""

from opsbrief.risks import SEVERITY_WEIGHT, Risk, RiskSeverity, priority_score


def make_risk(severity: RiskSeverity, *event_ids: str) -> Risk:
    """Return a risk of the given severity, backed by the given event ids."""
    return Risk(
        rule="rule",
        title="A concern",
        detail="Something the rule recognised.",
        severity=severity,
        event_ids=list(event_ids) or ["e1"],
    )


def test_every_severity_has_a_weight() -> None:
    assert set(SEVERITY_WEIGHT) == set(RiskSeverity)


def test_weights_increase_with_urgency() -> None:
    ordered = [RiskSeverity.LOW, RiskSeverity.MEDIUM, RiskSeverity.HIGH, RiskSeverity.CRITICAL]
    weights = [SEVERITY_WEIGHT[severity] for severity in ordered]

    assert weights == sorted(weights)
    assert len(set(weights)) == len(weights)


def test_score_is_the_severity_weight() -> None:
    for severity in RiskSeverity:
        assert priority_score(make_risk(severity)) == SEVERITY_WEIGHT[severity]


def test_a_more_urgent_risk_scores_higher() -> None:
    assert priority_score(make_risk(RiskSeverity.CRITICAL)) > priority_score(
        make_risk(RiskSeverity.LOW)
    )


def test_score_ignores_evidence_count() -> None:
    # The coarse score is severity alone; evidence only ever breaks ties.
    one = make_risk(RiskSeverity.HIGH, "e1")
    many = make_risk(RiskSeverity.HIGH, "e1", "e2", "e3")

    assert priority_score(one) == priority_score(many)
