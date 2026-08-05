"""Tests for the risk contract."""

import pytest
from pydantic import ValidationError

from opsbrief.risks import Risk, RiskSeverity


def make_risk(**overrides: object) -> dict[str, object]:
    """Return a valid risk payload with the given fields replaced."""
    payload: dict[str, object] = {
        "rule": "overdue_work",
        "title": "Safety inspection for fixture 4821 is overdue",
        "detail": "The inspection was due at 09:00 and is not yet resolved.",
        "severity": RiskSeverity.HIGH,
        "event_ids": ["e1", "e2"],
    }
    payload.update(overrides)
    return payload


def test_minimal_risk_is_accepted() -> None:
    risk = Risk(**make_risk())

    assert risk.rule == "overdue_work"
    assert risk.severity is RiskSeverity.HIGH
    assert risk.event_ids == ["e1", "e2"]


def test_severity_accepts_its_string_form() -> None:
    risk = Risk(**make_risk(severity="critical"))

    assert risk.severity is RiskSeverity.CRITICAL


def test_severity_has_no_info_level() -> None:
    # A risk always deserves attention, so the lowest level is 'low', not 'info'.
    assert "info" not in {level.value for level in RiskSeverity}
    assert {level.value for level in RiskSeverity} == {"low", "medium", "high", "critical"}


def test_a_risk_must_cite_at_least_one_event() -> None:
    with pytest.raises(ValidationError):
        Risk(**make_risk(event_ids=[]))


def test_event_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError) as error:
        Risk(**make_risk(event_ids=["e1", "e1"]))

    assert "unique" in str(error.value)


def test_event_ids_reject_a_blank_identifier() -> None:
    with pytest.raises(ValidationError):
        Risk(**make_risk(event_ids=["e1", "   "]))


def test_event_ids_order_is_preserved() -> None:
    risk = Risk(**make_risk(event_ids=["e3", "e1", "e2"]))

    assert risk.event_ids == ["e3", "e1", "e2"]


def test_rule_is_required() -> None:
    with pytest.raises(ValidationError):
        Risk(**make_risk(rule=""))


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Risk(**make_risk(extra="nope"))


def test_a_risk_is_serialisable() -> None:
    risk = Risk(**make_risk())

    dumped = risk.model_dump()

    assert dumped["rule"] == "overdue_work"
    assert dumped["severity"] == "high"
    assert dumped["event_ids"] == ["e1", "e2"]
