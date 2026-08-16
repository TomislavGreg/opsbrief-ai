"""Tests for declaring incidents from the risks recognised over stored events."""

from datetime import UTC, datetime, timedelta

from opsbrief.events import Event, EventInput
from opsbrief.incidents import (
    IncidentSeverity,
    IncidentStatus,
    declare_incidents_from_events,
)
from opsbrief.risks import Risk, RiskRule, RiskSeverity

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def make_event(event_id: str, **overrides: object) -> Event:
    """Return a stored event with the given id and fields replaced."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.due",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


class StubRule:
    """A rule that returns fixed risks, so a test can pin what detection yields."""

    def __init__(self, rule_id: str, risks: list[Risk]) -> None:
        self.rule_id = rule_id
        self._risks = risks

    def evaluate(self, events: list[Event]) -> list[Risk]:
        return list(self._risks)


def make_risk(severity: RiskSeverity, *event_ids: str, title: str = "A concern") -> Risk:
    """Return a risk of the given severity and evidence."""
    return Risk(
        rule="stub",
        title=title,
        detail="Something the rule recognised.",
        severity=severity,
        event_ids=list(event_ids),
    )


def test_no_events_declares_no_incidents() -> None:
    assert declare_incidents_from_events([], at=NOW) == []


def test_events_raising_no_risk_declare_no_incidents() -> None:
    # A task not yet due raises nothing under the default rules.
    event = make_event("e1", due_at=NOW + timedelta(hours=1))

    assert declare_incidents_from_events([event], at=NOW) == []


def test_a_real_overdue_event_becomes_an_open_incident() -> None:
    event = make_event("e1", due_at=NOW - timedelta(hours=2))

    incidents = declare_incidents_from_events([event], at=NOW)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident.status is IncidentStatus.OPEN
    assert incident.event_ids == ["e1"]
    assert incident.opened_at == NOW
    assert "overdue" in incident.title.lower()


def test_one_incident_is_declared_per_recognised_risk() -> None:
    rules = [
        StubRule(
            "stub",
            [
                make_risk(RiskSeverity.LOW, "e1", title="Low concern"),
                make_risk(RiskSeverity.HIGH, "e2", title="High concern"),
            ],
        )
    ]

    incidents = declare_incidents_from_events([], at=NOW, rules=rules)

    assert len(incidents) == 2
    assert {incident.title for incident in incidents} == {"Low concern", "High concern"}


def test_incidents_come_back_most_urgent_first() -> None:
    rules = [
        StubRule(
            "stub",
            [
                make_risk(RiskSeverity.LOW, "e1", title="Low concern"),
                make_risk(RiskSeverity.CRITICAL, "e2", title="Critical concern"),
                make_risk(RiskSeverity.MEDIUM, "e3", title="Medium concern"),
            ],
        )
    ]

    incidents = declare_incidents_from_events([], at=NOW, rules=rules)

    assert [incident.title for incident in incidents] == [
        "Critical concern",
        "Medium concern",
        "Low concern",
    ]
    assert [incident.severity for incident in incidents] == [
        IncidentSeverity.CRITICAL,
        IncidentSeverity.MEDIUM,
        IncidentSeverity.LOW,
    ]


def test_every_declared_incident_shares_the_reference_instant() -> None:
    rules = [
        StubRule(
            "stub",
            [
                make_risk(RiskSeverity.HIGH, "e1", title="First"),
                make_risk(RiskSeverity.HIGH, "e2", title="Second"),
            ],
        )
    ]

    incidents = declare_incidents_from_events([], at=NOW, rules=rules)

    assert all(incident.opened_at == NOW for incident in incidents)
    assert all(incident.updated_at == NOW for incident in incidents)


def test_the_stub_rule_satisfies_the_rule_protocol() -> None:
    # Guard the test double against drifting out of line with the protocol.
    assert isinstance(StubRule("stub", []), RiskRule)
