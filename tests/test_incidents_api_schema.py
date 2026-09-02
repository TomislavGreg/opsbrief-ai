"""Tests for the incident API request and page schemas."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from opsbrief.incidents import (
    DEFAULT_INCIDENT_PAGE_SIZE,
    MAX_INCIDENT_PAGE_SIZE,
    MAX_RESOLUTION_NOTE_LENGTH,
    Incident,
    IncidentDeclaration,
    IncidentPage,
    IncidentQuery,
    IncidentResolution,
    IncidentSeverity,
    IncidentStatus,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def make_incident(incident_id: str = "inc-1") -> Incident:
    """Declare an incident for use in a page."""
    return Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=["e17", "e18"],
        at=NOW,
        incident_id=incident_id,
    )


def test_a_declaration_carries_the_posted_fields() -> None:
    declaration = IncidentDeclaration(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=["e17", "e18"],
    )

    assert declaration.title == "Ticketing integration failing repeatedly"
    assert declaration.severity is IncidentSeverity.HIGH
    assert declaration.event_ids == ["e17", "e18"]


def test_a_declaration_needs_at_least_one_event() -> None:
    with pytest.raises(ValidationError):
        IncidentDeclaration(title="No evidence", severity=IncidentSeverity.LOW, event_ids=[])


def test_a_declaration_rejects_blank_event_ids() -> None:
    with pytest.raises(ValidationError):
        IncidentDeclaration(title="Blank", severity=IncidentSeverity.LOW, event_ids=["e1", "  "])


def test_a_declaration_rejects_repeated_event_ids() -> None:
    with pytest.raises(ValidationError):
        IncidentDeclaration(title="Dup", severity=IncidentSeverity.LOW, event_ids=["e1", "e1"])


def test_a_declaration_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IncidentDeclaration(
            title="Extra",
            severity=IncidentSeverity.LOW,
            event_ids=["e1"],
            status=IncidentStatus.OPEN,
        )


def test_a_declaration_carries_no_status_field() -> None:
    # The service starts every declared incident open, so the body cannot set it.
    assert "status" not in IncidentDeclaration.model_fields


def test_a_resolution_defaults_to_no_note() -> None:
    assert IncidentResolution().note is None


def test_a_resolution_carries_and_trims_its_note() -> None:
    resolution = IncidentResolution(note="  Restarted the sync.  ")

    assert resolution.note == "Restarted the sync."


def test_a_resolution_treats_a_blank_note_as_none() -> None:
    assert IncidentResolution(note="   ").note is None


def test_a_resolution_rejects_an_over_long_note() -> None:
    with pytest.raises(ValidationError):
        IncidentResolution(note="x" * (MAX_RESOLUTION_NOTE_LENGTH + 1))


def test_a_resolution_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IncidentResolution(status=IncidentStatus.RESOLVED)


def test_a_query_defaults_to_no_filter_and_the_default_page() -> None:
    query = IncidentQuery()

    assert query.status is None
    assert query.severity is None
    assert query.opened_from is None
    assert query.opened_to is None
    assert query.limit == DEFAULT_INCIDENT_PAGE_SIZE
    assert query.offset == 0


def test_a_query_carries_the_severity_filter() -> None:
    query = IncidentQuery(severity=IncidentSeverity.CRITICAL)

    assert query.severity is IncidentSeverity.CRITICAL


def test_a_query_normalises_opened_bounds_to_utc() -> None:
    query = IncidentQuery(
        opened_from="2026-08-16T14:00:00+02:00",
        opened_to="2026-08-16T18:00:00+02:00",
    )

    assert query.opened_from == datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
    assert query.opened_to == datetime(2026, 8, 16, 16, 0, tzinfo=UTC)


def test_a_query_rejects_an_opened_bound_without_an_offset() -> None:
    with pytest.raises(ValidationError):
        IncidentQuery(opened_from="2026-08-16T14:00:00")


def test_a_query_rejects_an_inverted_opened_window() -> None:
    with pytest.raises(ValidationError):
        IncidentQuery(opened_from=NOW, opened_to=NOW - timedelta(hours=1))


def test_a_query_rejects_a_limit_above_the_maximum() -> None:
    with pytest.raises(ValidationError):
        IncidentQuery(limit=MAX_INCIDENT_PAGE_SIZE + 1)


def test_a_query_rejects_a_zero_limit() -> None:
    with pytest.raises(ValidationError):
        IncidentQuery(limit=0)


def test_a_query_rejects_a_negative_offset() -> None:
    with pytest.raises(ValidationError):
        IncidentQuery(offset=-1)


def test_a_query_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IncidentQuery(state=IncidentStatus.OPEN)


def test_a_page_reports_its_totals_and_incidents() -> None:
    page = IncidentPage(total=3, limit=50, offset=0, incidents=[make_incident()])

    assert page.total == 3
    assert page.limit == 50
    assert page.offset == 0
    assert [incident.id for incident in page.incidents] == ["inc-1"]
