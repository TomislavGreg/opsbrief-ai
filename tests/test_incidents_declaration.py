"""Tests for declaring an incident from a risk."""

from datetime import UTC, datetime

import pytest

from opsbrief.incidents import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    declare_incident_from_risk,
)
from opsbrief.risks import Risk, RiskSeverity

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def make_risk(**overrides: object) -> Risk:
    """Build a risk with sensible defaults for the fields under test."""
    payload: dict[str, object] = {
        "rule": "repeated_integration_failure",
        "title": "Integration ticketing has failed 5 times",
        "detail": 'Integration "ticketing" has failed 5 times without recovering.',
        "severity": RiskSeverity.CRITICAL,
        "event_ids": ["e17", "e18", "e19", "e20", "e21"],
    }
    payload.update(overrides)
    return Risk(**payload)


def test_declaring_carries_the_risk_title_and_events() -> None:
    incident = declare_incident_from_risk(make_risk(), at=NOW, incident_id="inc-1")

    assert isinstance(incident, Incident)
    assert incident.id == "inc-1"
    assert incident.title == "Integration ticketing has failed 5 times"
    assert incident.event_ids == ["e17", "e18", "e19", "e20", "e21"]


def test_a_declared_incident_starts_open_at_the_given_instant() -> None:
    incident = declare_incident_from_risk(make_risk(), at=NOW)

    assert incident.status is IncidentStatus.OPEN
    assert incident.is_active
    assert incident.opened_at == NOW
    assert incident.updated_at == NOW
    assert incident.resolved_at is None


@pytest.mark.parametrize(
    ("risk_severity", "incident_severity"),
    [
        (RiskSeverity.LOW, IncidentSeverity.LOW),
        (RiskSeverity.MEDIUM, IncidentSeverity.MEDIUM),
        (RiskSeverity.HIGH, IncidentSeverity.HIGH),
        (RiskSeverity.CRITICAL, IncidentSeverity.CRITICAL),
    ],
)
def test_severity_maps_one_to_one(
    risk_severity: RiskSeverity, incident_severity: IncidentSeverity
) -> None:
    incident = declare_incident_from_risk(make_risk(severity=risk_severity), at=NOW)

    assert incident.severity is incident_severity


def test_the_events_keep_the_order_the_risk_cites_them() -> None:
    risk = make_risk(event_ids=["e21", "e17", "e19"])

    incident = declare_incident_from_risk(risk, at=NOW)

    assert incident.event_ids == ["e21", "e17", "e19"]


def test_the_incident_does_not_share_the_risks_event_list() -> None:
    risk = make_risk(event_ids=["e17", "e18"])

    incident = declare_incident_from_risk(risk, at=NOW)
    incident.event_ids.append("e99")

    assert risk.event_ids == ["e17", "e18"]


def test_an_omitted_id_gets_a_fresh_identifier() -> None:
    first = declare_incident_from_risk(make_risk(), at=NOW)
    second = declare_incident_from_risk(make_risk(), at=NOW)

    assert first.id
    assert first.id != second.id
