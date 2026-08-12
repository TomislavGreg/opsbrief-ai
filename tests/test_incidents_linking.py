"""Tests for attaching and detaching events on an incident."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from opsbrief.incidents import (
    Incident,
    IncidentClosedError,
    IncidentSeverity,
    IncidentStatus,
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


def test_linking_appends_new_events_in_order() -> None:
    later = OPENED + timedelta(hours=1)
    incident = make_incident().link_events(["e3", "e4"], at=later)

    assert incident.event_ids == ["e1", "e2", "e3", "e4"]
    assert incident.updated_at == later
    assert incident.opened_at == OPENED


def test_linking_is_idempotent_for_already_linked_events() -> None:
    incident = make_incident().link_events(["e2", "e3", "e2"], at=OPENED + timedelta(hours=1))

    # e2 stays where it was, e3 is appended once, the repeat is ignored.
    assert incident.event_ids == ["e1", "e2", "e3"]


def test_linking_rejects_a_blank_identifier() -> None:
    with pytest.raises(ValueError, match="blank"):
        make_incident().link_events(["e3", "  "])


def test_linking_leaves_the_original_untouched() -> None:
    incident = make_incident()
    linked = incident.link_events(["e3"], at=OPENED + timedelta(hours=1))

    assert incident.event_ids == ["e1", "e2"]
    assert linked is not incident


def test_cannot_link_events_to_a_closed_incident() -> None:
    closed = make_incident().transition_to(IncidentStatus.CLOSED, at=OPENED + timedelta(hours=1))

    with pytest.raises(IncidentClosedError) as error:
        closed.link_events(["e3"])

    assert error.value.incident_id == "inc-1"
    assert "link events" in str(error.value)


def test_linking_is_allowed_on_a_resolved_incident() -> None:
    resolved = make_incident().transition_to(
        IncidentStatus.RESOLVED, at=OPENED + timedelta(hours=1)
    )
    linked = resolved.link_events(["e3"], at=OPENED + timedelta(hours=2))

    # A resolved incident is not frozen; only a closed one is.
    assert linked.event_ids == ["e1", "e2", "e3"]
    assert linked.status is IncidentStatus.RESOLVED


def test_unlinking_removes_the_named_events() -> None:
    later = OPENED + timedelta(hours=1)
    incident = make_incident(event_ids=["e1", "e2", "e3"]).unlink_events(["e2"], at=later)

    assert incident.event_ids == ["e1", "e3"]
    assert incident.updated_at == later


def test_unlinking_ignores_events_that_are_not_linked() -> None:
    incident = make_incident().unlink_events(["e9"], at=OPENED + timedelta(hours=1))

    assert incident.event_ids == ["e1", "e2"]


def test_unlinking_cannot_remove_the_last_event() -> None:
    with pytest.raises(ValueError, match="at least one source event"):
        make_incident(event_ids=["e1"]).unlink_events(["e1"])


def test_unlinking_all_events_is_refused_even_across_several() -> None:
    with pytest.raises(ValueError, match="at least one source event"):
        make_incident(event_ids=["e1", "e2"]).unlink_events(["e1", "e2"])


def test_cannot_unlink_events_from_a_closed_incident() -> None:
    closed = make_incident(event_ids=["e1", "e2"]).transition_to(
        IncidentStatus.CLOSED, at=OPENED + timedelta(hours=1)
    )

    with pytest.raises(IncidentClosedError) as error:
        closed.unlink_events(["e2"])

    assert "unlink events" in str(error.value)


def test_the_evidence_invariant_survives_a_direct_construction() -> None:
    # The model itself still refuses an empty evidence list, independent of unlink.
    with pytest.raises(ValidationError):
        make_incident(event_ids=[])
