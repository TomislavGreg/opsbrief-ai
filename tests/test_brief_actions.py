"""Tests for deterministic suggested next actions."""

from opsbrief.brief.actions import (
    DEFAULT_ACTION,
    RECOMMENDED_ACTIONS,
    NextAction,
    suggest_next_actions,
)
from opsbrief.risks import Risk, RiskSeverity


def make_risk(
    *,
    rule: str = "overdue_work",
    title: str = "Safety inspection for North Stand is overdue",
    severity: RiskSeverity = RiskSeverity.HIGH,
    event_ids: list[str] | None = None,
) -> Risk:
    return Risk(
        rule=rule,
        title=title,
        detail="Deterministic explanation naming the evidence.",
        severity=severity,
        event_ids=event_ids or ["e04"],
    )


def test_no_risks_yields_no_actions() -> None:
    assert suggest_next_actions([]) == []


def test_one_action_per_risk_in_order() -> None:
    risks = [
        make_risk(rule="repeated_integration_failure", severity=RiskSeverity.CRITICAL),
        make_risk(rule="overdue_work", severity=RiskSeverity.HIGH),
        make_risk(rule="blocked_work", severity=RiskSeverity.MEDIUM),
    ]

    actions = suggest_next_actions(risks)

    assert [a.rule for a in actions] == [r.rule for r in risks]
    assert all(isinstance(a, NextAction) for a in actions)


def test_action_carries_the_risk_evidence_and_severity() -> None:
    risk = make_risk(rule="blocked_work", severity=RiskSeverity.MEDIUM, event_ids=["e10", "e11"])

    (action,) = suggest_next_actions([risk])

    assert action.action == RECOMMENDED_ACTIONS["blocked_work"]
    assert action.title == risk.title
    assert action.severity is RiskSeverity.MEDIUM
    assert action.event_ids == ["e10", "e11"]


def test_each_known_rule_has_a_canonical_action() -> None:
    for rule, expected in RECOMMENDED_ACTIONS.items():
        (action,) = suggest_next_actions([make_risk(rule=rule)])
        assert action.action == expected


def test_an_unknown_rule_falls_back_to_the_default_action() -> None:
    (action,) = suggest_next_actions([make_risk(rule="some_future_rule")])

    assert action.action == DEFAULT_ACTION


def test_the_action_does_not_alias_the_risk_event_ids() -> None:
    risk = make_risk(event_ids=["e04"])

    (action,) = suggest_next_actions([risk])
    action.event_ids.append("e99")

    assert risk.event_ids == ["e04"]
