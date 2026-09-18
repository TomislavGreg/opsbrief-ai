"""Tests for the deterministic offline incident narrative (AI-111)."""

from datetime import UTC, datetime

from opsbrief.events import EventSeverity, EventStatus
from opsbrief.incidents import Incident, IncidentSeverity, IncidentStatus
from opsbrief.incidents.narrative import compose_incident_narrative
from opsbrief.incidents.timeline import IncidentTimeline, TimelineEntry

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 8, 9, 13, 30, tzinfo=UTC)


def make_incident(
    *,
    status: IncidentStatus = IncidentStatus.INVESTIGATING,
    resolution_note: str | None = None,
) -> Incident:
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=["e17", "e18"],
        at=NOW,
        incident_id="incident-1",
    )
    incident = incident.model_copy(
        update={"status": status, "resolution_note": resolution_note, "updated_at": LATER}
    )
    return incident


def make_timeline(*, entries: int = 2, missing: list[str] | None = None) -> IncidentTimeline:
    made = [
        TimelineEntry(
            id=f"e{17 + i}",
            source="integrations",
            event_type="integration.failed",
            subject="Ticketing webhook failed",
            occurred_at=NOW if i == 0 else LATER,
            severity=EventSeverity.HIGH,
            status=EventStatus.FAILED,
        )
        for i in range(entries)
    ]
    return IncidentTimeline(incident_id="incident-1", entries=made, missing_event_ids=missing or [])


def test_the_narrative_states_status_severity_span_and_size() -> None:
    narrative = compose_incident_narrative(make_incident(), make_timeline())

    assert (
        'Incident "Ticketing integration failing repeatedly" is investigating (high).' in narrative
    )
    assert "2 events" in narrative
    assert NOW.isoformat() in narrative
    assert LATER.isoformat() in narrative


def test_no_resolving_events_is_stated_plainly() -> None:
    narrative = compose_incident_narrative(make_incident(), make_timeline(entries=0))

    assert "no timeline to describe" in narrative.lower()


def test_missing_citations_are_named() -> None:
    narrative = compose_incident_narrative(make_incident(), make_timeline(missing=["e18"]))

    assert "1 cited event no longer resolve" in narrative


def test_a_resolution_note_is_carried_when_resolved() -> None:
    incident = make_incident(status=IncidentStatus.RESOLVED, resolution_note="Restarted the sync.")
    narrative = compose_incident_narrative(incident, make_timeline())

    assert "Resolved: Restarted the sync." in narrative


def test_an_active_incident_carries_no_resolution() -> None:
    narrative = compose_incident_narrative(make_incident(), make_timeline())

    assert "Resolved:" not in narrative


def test_the_narrative_is_stable_for_equal_inputs() -> None:
    assert compose_incident_narrative(make_incident(), make_timeline()) == (
        compose_incident_narrative(make_incident(), make_timeline())
    )


def test_excluded_occurrence_holds_back_the_span() -> None:
    narrative = compose_incident_narrative(
        make_incident(), make_timeline(), excluded_fields={"occurred_at"}
    )

    assert NOW.isoformat() not in narrative
    assert "[excluded]" in narrative
