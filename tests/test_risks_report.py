"""Tests for the risk-snapshot model and the canonical rule set."""

from datetime import UTC, datetime

from opsbrief.risks import (
    BlockedWorkRule,
    OverdueWorkRule,
    RepeatedIntegrationFailureRule,
    Risk,
    RiskList,
    RiskRule,
    RiskSeverity,
    default_rules,
)

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


def make_risk(severity: RiskSeverity = RiskSeverity.HIGH, *event_ids: str) -> Risk:
    """Return a risk of the given severity, backed by the given event ids."""
    return Risk(
        rule="rule",
        title="A concern",
        detail="Something the rule recognised.",
        severity=severity,
        event_ids=list(event_ids) or ["e1"],
    )


def test_total_counts_the_risks() -> None:
    snapshot = RiskList(generated_at=NOW, risks=[make_risk(), make_risk()])

    assert snapshot.total == 2


def test_total_is_zero_for_an_empty_snapshot() -> None:
    assert RiskList(generated_at=NOW, risks=[]).total == 0


def test_total_is_serialised() -> None:
    snapshot = RiskList(generated_at=NOW, risks=[make_risk()])

    dumped = snapshot.model_dump()

    assert dumped["total"] == 1
    assert dumped["generated_at"] == NOW


def test_default_rules_covers_every_implemented_rule() -> None:
    rules = default_rules(NOW)
    types = {type(rule) for rule in rules}

    assert types == {OverdueWorkRule, BlockedWorkRule, RepeatedIntegrationFailureRule}


def test_default_rules_all_satisfy_the_protocol() -> None:
    assert all(isinstance(rule, RiskRule) for rule in default_rules(NOW))


def test_default_rules_share_the_reference_instant() -> None:
    # Every rule judges against the one instant it was given.
    rules = default_rules(NOW)

    assert all(getattr(rule, "_now", NOW) == NOW for rule in rules)
