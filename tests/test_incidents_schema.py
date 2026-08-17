"""Tests for the incident contract and its lifecycle transitions."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from opsbrief.incidents import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    InvalidIncidentTransition,
)

OPENED = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)


def make_incident(**overrides: object) -> Incident:
    """Return a freshly declared incident with the given fields replaced."""
    payload: dict[str, object] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": IncidentSeverity.HIGH,
        "event_ids": ["e1", "e2"],
        "at": OPENED,
        "incident_id": "inc-1",
    }
    payload.update(overrides)
    return Incident.declare(**payload)  # type: ignore[arg-type]


def test_declare_opens_an_incident() -> None:
    incident = make_incident()

    assert incident.id == "inc-1"
    assert incident.status is IncidentStatus.OPEN
    assert incident.severity is IncidentSeverity.HIGH
    assert incident.opened_at == OPENED
    assert incident.updated_at == OPENED
    assert incident.resolved_at is None
    assert incident.event_ids == ["e1", "e2"]
    assert incident.is_active is True
    assert incident.is_terminal is False


def test_declare_assigns_an_id_when_none_is_given() -> None:
    incident = Incident.declare(
        title="Power alert", severity=IncidentSeverity.CRITICAL, event_ids=["e9"], at=OPENED
    )

    assert incident.id
    assert incident.status is IncidentStatus.OPEN


def test_severity_has_no_info_level() -> None:
    assert {level.value for level in IncidentSeverity} == {"low", "medium", "high", "critical"}


def test_an_incident_must_cite_at_least_one_event() -> None:
    with pytest.raises(ValidationError):
        make_incident(event_ids=[])


def test_event_ids_must_be_unique() -> None:
    with pytest.raises(ValidationError) as error:
        make_incident(event_ids=["e1", "e1"])

    assert "unique" in str(error.value)


def test_event_ids_reject_a_blank_identifier() -> None:
    with pytest.raises(ValidationError):
        make_incident(event_ids=["e1", "  "])


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Incident(
            id="inc-1",
            title="x",
            status=IncidentStatus.OPEN,
            severity=IncidentSeverity.LOW,
            opened_at=OPENED,
            updated_at=OPENED,
            event_ids=["e1"],
            extra="nope",
        )


def test_timestamps_without_an_offset_are_refused() -> None:
    with pytest.raises(ValidationError):
        make_incident(at=datetime(2026, 8, 12, 9, 0))  # noqa: DTZ001


def test_an_active_incident_may_not_carry_a_resolution_instant() -> None:
    with pytest.raises(ValidationError) as error:
        Incident(
            id="inc-1",
            title="x",
            status=IncidentStatus.INVESTIGATING,
            severity=IncidentSeverity.LOW,
            opened_at=OPENED,
            updated_at=OPENED,
            resolved_at=OPENED,
            event_ids=["e1"],
        )

    assert "resolved_at" in str(error.value)


def test_an_inactive_incident_needs_a_resolution_instant() -> None:
    with pytest.raises(ValidationError) as error:
        Incident(
            id="inc-1",
            title="x",
            status=IncidentStatus.RESOLVED,
            severity=IncidentSeverity.LOW,
            opened_at=OPENED,
            updated_at=OPENED,
            resolved_at=None,
            event_ids=["e1"],
        )

    assert "resolved_at" in str(error.value)


def test_updated_at_cannot_precede_opened_at() -> None:
    with pytest.raises(ValidationError):
        Incident(
            id="inc-1",
            title="x",
            status=IncidentStatus.OPEN,
            severity=IncidentSeverity.LOW,
            opened_at=OPENED,
            updated_at=OPENED - timedelta(hours=1),
            event_ids=["e1"],
        )


def test_transition_advances_status_and_update_time() -> None:
    later = OPENED + timedelta(hours=1)
    incident = make_incident().transition_to(IncidentStatus.INVESTIGATING, at=later)

    assert incident.status is IncidentStatus.INVESTIGATING
    assert incident.updated_at == later
    assert incident.opened_at == OPENED
    assert incident.resolved_at is None


def test_resolving_records_the_resolution_instant() -> None:
    resolved_at = OPENED + timedelta(hours=2)
    incident = make_incident().transition_to(IncidentStatus.RESOLVED, at=resolved_at)

    assert incident.status is IncidentStatus.RESOLVED
    assert incident.resolved_at == resolved_at
    assert incident.is_active is False


def test_closing_a_resolved_incident_keeps_the_original_resolution_instant() -> None:
    resolved_at = OPENED + timedelta(hours=2)
    closed_at = OPENED + timedelta(hours=5)
    incident = (
        make_incident()
        .transition_to(IncidentStatus.RESOLVED, at=resolved_at)
        .transition_to(IncidentStatus.CLOSED, at=closed_at)
    )

    assert incident.status is IncidentStatus.CLOSED
    assert incident.resolved_at == resolved_at
    assert incident.is_terminal is True


def test_closing_an_active_incident_records_the_closing_instant() -> None:
    closed_at = OPENED + timedelta(hours=3)
    incident = make_incident().transition_to(IncidentStatus.CLOSED, at=closed_at)

    assert incident.status is IncidentStatus.CLOSED
    assert incident.resolved_at == closed_at


def test_reopening_a_resolved_incident_clears_the_resolution_instant() -> None:
    incident = (
        make_incident()
        .transition_to(IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=2))
        .transition_to(IncidentStatus.INVESTIGATING, at=OPENED + timedelta(hours=4))
    )

    assert incident.status is IncidentStatus.INVESTIGATING
    assert incident.resolved_at is None
    assert incident.is_active is True


def test_resolving_records_a_resolution_note() -> None:
    incident = make_incident().transition_to(
        IncidentStatus.RESOLVED,
        at=OPENED + timedelta(hours=2),
        note="Restarted the ticketing sync.",
    )

    assert incident.status is IncidentStatus.RESOLVED
    assert incident.resolution_note == "Restarted the ticketing sync."


def test_a_resolution_note_is_optional() -> None:
    incident = make_incident().transition_to(
        IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=1)
    )

    assert incident.status is IncidentStatus.RESOLVED
    assert incident.resolution_note is None


def test_a_blank_resolution_note_is_treated_as_none() -> None:
    incident = make_incident().transition_to(
        IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=1), note="   "
    )

    assert incident.resolution_note is None


def test_a_resolution_note_is_trimmed() -> None:
    incident = make_incident().transition_to(
        IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=1), note="  cleared the backlog  "
    )

    assert incident.resolution_note == "cleared the backlog"


def test_closing_a_resolved_incident_keeps_its_resolution_note() -> None:
    incident = (
        make_incident()
        .transition_to(IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=2), note="Fixed.")
        .transition_to(IncidentStatus.CLOSED, at=OPENED + timedelta(hours=5))
    )

    assert incident.resolution_note == "Fixed."


def test_closing_with_a_new_note_replaces_the_earlier_one() -> None:
    incident = (
        make_incident()
        .transition_to(IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=2), note="Mitigated.")
        .transition_to(IncidentStatus.CLOSED, at=OPENED + timedelta(hours=5), note="Signed off.")
    )

    assert incident.resolution_note == "Signed off."


def test_reopening_a_resolved_incident_clears_its_resolution_note() -> None:
    incident = (
        make_incident()
        .transition_to(IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=2), note="Fixed.")
        .transition_to(IncidentStatus.INVESTIGATING, at=OPENED + timedelta(hours=4))
    )

    assert incident.status is IncidentStatus.INVESTIGATING
    assert incident.resolution_note is None


def test_a_note_cannot_be_recorded_when_reopening() -> None:
    resolved = make_incident().transition_to(
        IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=2)
    )

    with pytest.raises(ValueError, match="reopening"):
        resolved.transition_to(
            IncidentStatus.INVESTIGATING, at=OPENED + timedelta(hours=4), note="x"
        )


def test_an_over_long_resolution_note_is_refused() -> None:
    with pytest.raises(ValueError, match="at most"):
        make_incident().transition_to(
            IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=1), note="x" * 2_001
        )


def test_an_active_incident_may_not_carry_a_resolution_note() -> None:
    with pytest.raises(ValidationError) as error:
        Incident(
            id="inc-1",
            title="x",
            status=IncidentStatus.OPEN,
            severity=IncidentSeverity.LOW,
            opened_at=OPENED,
            updated_at=OPENED,
            resolution_note="not allowed while active",
            event_ids=["e1"],
        )

    assert "resolution_note" in str(error.value)


def test_a_disallowed_transition_raises_and_changes_nothing() -> None:
    resolved = make_incident().transition_to(IncidentStatus.CLOSED, at=OPENED + timedelta(hours=1))

    with pytest.raises(InvalidIncidentTransition) as error:
        resolved.transition_to(IncidentStatus.OPEN)

    assert error.value.current is IncidentStatus.CLOSED
    assert error.value.target is IncidentStatus.OPEN


def test_transition_returns_a_copy_and_leaves_the_original_untouched() -> None:
    incident = make_incident()
    moved = incident.transition_to(IncidentStatus.INVESTIGATING, at=OPENED + timedelta(hours=1))

    assert incident.status is IncidentStatus.OPEN
    assert moved is not incident


def test_an_incident_is_serialisable() -> None:
    dumped = make_incident().model_dump()

    assert dumped["status"] == "open"
    assert dumped["severity"] == "high"
    assert dumped["event_ids"] == ["e1", "e2"]
    assert dumped["is_active"] is True
    assert dumped["is_terminal"] is False
