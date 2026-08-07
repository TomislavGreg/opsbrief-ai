"""Tests for risk priority scoring."""

from opsbrief.risks import (
    SEVERITY_WEIGHT,
    Risk,
    RiskSeverity,
    prioritize,
    priority_score,
)


def make_risk(
    severity: RiskSeverity,
    *event_ids: str,
    rule: str = "rule",
    title: str = "A concern",
) -> Risk:
    """Return a risk of the given severity, backed by the given event ids."""
    return Risk(
        rule=rule,
        title=title,
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


def test_prioritize_orders_by_severity_first() -> None:
    low = make_risk(RiskSeverity.LOW, "a")
    critical = make_risk(RiskSeverity.CRITICAL, "b")
    medium = make_risk(RiskSeverity.MEDIUM, "c")
    high = make_risk(RiskSeverity.HIGH, "d")

    ordered = prioritize([low, critical, medium, high])

    assert [risk.severity for risk in ordered] == [
        RiskSeverity.CRITICAL,
        RiskSeverity.HIGH,
        RiskSeverity.MEDIUM,
        RiskSeverity.LOW,
    ]


def test_severity_dominates_evidence() -> None:
    # A wall of evidence never lifts a lower severity above a higher one.
    high_thin = make_risk(RiskSeverity.HIGH, "a")
    medium_thick = make_risk(RiskSeverity.MEDIUM, "b", "c", "d", "e", "f")

    assert prioritize([medium_thick, high_thin]) == [high_thin, medium_thick]


def test_evidence_breaks_ties_within_a_severity() -> None:
    thin = make_risk(RiskSeverity.HIGH, "a")
    thick = make_risk(RiskSeverity.HIGH, "b", "c", "d")

    ordered = prioritize([thin, thick])

    assert [risk.event_ids for risk in ordered] == [["b", "c", "d"], ["a"]]


def test_remaining_ties_break_by_rule_then_title_then_event() -> None:
    first = make_risk(RiskSeverity.HIGH, "e1", rule="alpha", title="A")
    by_title = make_risk(RiskSeverity.HIGH, "e2", rule="beta", title="A")
    by_rule = make_risk(RiskSeverity.HIGH, "e3", rule="beta", title="B")

    ordered = prioritize([by_rule, by_title, first])

    assert ordered == [first, by_title, by_rule]


def test_prioritize_is_deterministic_regardless_of_input_order() -> None:
    risks = [
        make_risk(RiskSeverity.LOW, "a"),
        make_risk(RiskSeverity.CRITICAL, "b"),
        make_risk(RiskSeverity.HIGH, "c"),
        make_risk(RiskSeverity.HIGH, "d", "e"),
    ]

    assert prioritize(risks) == prioritize(list(reversed(risks)))


def test_prioritize_leaves_the_input_untouched() -> None:
    risks = [make_risk(RiskSeverity.LOW, "a"), make_risk(RiskSeverity.CRITICAL, "b")]
    before = list(risks)

    prioritize(risks)

    assert risks == before


def test_prioritize_of_nothing_is_nothing() -> None:
    assert prioritize([]) == []
