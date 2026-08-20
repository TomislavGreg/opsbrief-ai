"""Tests for resolving cited event identifiers into source references."""

from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.events import Event, EventInput, EventSeverity, EventStatus
from opsbrief.references import SourceReference, build_source_references

NOW = datetime(2026, 8, 20, 18, 0, tzinfo=UTC)


def make_event(event_id: str, *, minutes_ago: int = 0, **overrides: object) -> Event:
    """Build a stored event with the given id and occurrence time."""
    payload: dict[str, object] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": f"Failure {event_id}",
        "occurred_at": NOW - timedelta(minutes=minutes_ago),
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def test_a_resolved_reference_describes_the_stored_event() -> None:
    event = make_event("e1", minutes_ago=30, subject="Ticketing webhook failed")

    references = build_source_references(["e1"], [event])

    assert len(references) == 1
    reference = references[0]
    assert reference == SourceReference(
        event_id="e1",
        resolved=True,
        source="integrations",
        event_type="integration.failed",
        subject="Ticketing webhook failed",
        occurred_at=event.occurred_at,
        severity=EventSeverity.HIGH,
        status=EventStatus.FAILED,
    )


def test_a_cited_id_no_event_answers_to_is_marked_unresolved() -> None:
    references = build_source_references(["missing"], [make_event("e1")])

    assert references == [SourceReference(event_id="missing", resolved=False)]
    unresolved = references[0]
    assert unresolved.source is None
    assert unresolved.event_type is None
    assert unresolved.subject is None
    assert unresolved.occurred_at is None
    assert unresolved.severity is None
    assert unresolved.status is None


def test_references_follow_the_order_of_the_ids_not_the_events() -> None:
    events = [make_event("e1"), make_event("e2"), make_event("e3")]

    references = build_source_references(["e3", "e1", "e2"], events)

    assert [reference.event_id for reference in references] == ["e3", "e1", "e2"]
    assert all(reference.resolved for reference in references)


def test_every_cited_id_is_accounted_for_once_resolved_or_missing() -> None:
    events = [make_event("e1"), make_event("e2")]

    references = build_source_references(["e1", "gone", "e2"], events)

    assert [(r.event_id, r.resolved) for r in references] == [
        ("e1", True),
        ("gone", False),
        ("e2", True),
    ]


def test_a_repeated_id_yields_a_reference_each_time_it_appears() -> None:
    references = build_source_references(["e1", "e1"], [make_event("e1")])

    assert [reference.event_id for reference in references] == ["e1", "e1"]
    assert all(reference.resolved for reference in references)


def test_no_cited_ids_yields_no_references() -> None:
    assert build_source_references([], [make_event("e1")]) == []


def test_an_event_carrying_no_status_resolves_with_a_null_status() -> None:
    event = make_event("e1", status=None)

    references = build_source_references(["e1"], [event])

    assert references[0].resolved is True
    assert references[0].status is None


def test_the_events_given_are_not_mutated() -> None:
    events = [make_event("e1"), make_event("e2")]
    before = [event.model_copy(deep=True) for event in events]

    build_source_references(["e1"], events)

    assert events == before


def test_a_reference_forbids_unknown_fields() -> None:
    with pytest.raises(ValueError):
        SourceReference(event_id="e1", resolved=True, unexpected="x")
