"""Tests for assembling the daily-brief context from stored events."""

from datetime import UTC, datetime, timedelta

from opsbrief.brief import DEFAULT_RECENT_EVENTS, build_brief_context
from opsbrief.events import Event, EventInput, EventSeverity, EventStatus

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def make_event(event_id: str, **overrides: object) -> Event:
    """Build a stored event with the given id and fields."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    return Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})


def test_no_events_yields_an_empty_traceable_context() -> None:
    context = build_brief_context([], NOW)

    assert context.generated_at == NOW
    assert context.event_count == 0
    assert context.risks == []
    assert context.recent_events == []
    assert context.source_event_ids == []
    assert context.notes == [
        "No operational events have been recorded, so the brief has no source data."
    ]


def test_reference_instant_is_normalised_to_utc() -> None:
    naive_offset = datetime(2026, 8, 9, 14, 0, tzinfo=UTC).astimezone()

    context = build_brief_context([], naive_offset)

    assert context.generated_at == datetime(2026, 8, 9, 14, 0, tzinfo=UTC)


def test_overdue_event_becomes_a_traceable_risk() -> None:
    events = [make_event("late", due_at=NOW - timedelta(hours=2))]

    context = build_brief_context(events, NOW)

    assert [risk.rule for risk in context.risks] == ["overdue_work"]
    assert context.risks[0].event_ids == ["late"]
    assert "late" in context.source_event_ids


def test_risks_are_judged_over_all_events_not_just_recent() -> None:
    # One overdue event well before a cap's worth of newer, benign events.
    events = [
        make_event("late", due_at=NOW - timedelta(days=3), occurred_at=NOW - timedelta(days=3))
    ]
    for index in range(5):
        events.append(make_event(f"noise{index}", occurred_at=NOW - timedelta(minutes=index)))

    context = build_brief_context(events, NOW, max_recent_events=2)

    # The overdue event is older than the recent-events cap, but the risk still fires.
    assert [risk.rule for risk in context.risks] == ["overdue_work"]
    assert context.risks[0].event_ids == ["late"]
    assert "late" not in [digest.id for digest in context.recent_events]
    # ...and it is still traceable, because risks contribute their events first.
    assert context.source_event_ids[0] == "late"


def test_references_resolve_every_source_event_id_in_the_same_order() -> None:
    events = [
        make_event("late", due_at=NOW - timedelta(hours=2), subject="Overdue safety check"),
        make_event("recent", occurred_at=NOW - timedelta(minutes=5)),
    ]

    context = build_brief_context(events, NOW)

    # One reference per source event id, in the same order, each resolved.
    assert [reference.event_id for reference in context.references] == context.source_event_ids
    assert all(reference.resolved for reference in context.references)
    by_id = {reference.event_id: reference for reference in context.references}
    assert by_id["late"].subject == "Overdue safety check"
    assert by_id["late"].source == "tasks"


def test_no_events_yields_no_references() -> None:
    context = build_brief_context([], NOW)

    assert context.references == []


def test_no_risks_over_benign_events_is_noted() -> None:
    events = [make_event("ok", due_at=NOW + timedelta(days=1))]

    context = build_brief_context(events, NOW)

    assert context.risks == []
    assert context.notes == ["No risks were detected across the 1 events considered."]


def test_recent_events_are_newest_first_and_carry_the_digest_fields() -> None:
    events = [
        make_event("old", occurred_at=NOW - timedelta(hours=3), severity=EventSeverity.LOW),
        make_event(
            "new",
            occurred_at=NOW - timedelta(hours=1),
            severity=EventSeverity.HIGH,
            status=EventStatus.OPEN,
        ),
    ]

    context = build_brief_context(events, NOW)

    assert [digest.id for digest in context.recent_events] == ["new", "old"]
    newest = context.recent_events[0]
    assert newest.severity is EventSeverity.HIGH
    assert newest.status is EventStatus.OPEN
    assert newest.subject == "Work item new"


def test_recent_events_ties_broken_by_id_deterministically() -> None:
    same_instant = NOW - timedelta(hours=1)
    events = [
        make_event("b", occurred_at=same_instant),
        make_event("a", occurred_at=same_instant),
        make_event("c", occurred_at=same_instant),
    ]

    context = build_brief_context(events, NOW)

    assert [digest.id for digest in context.recent_events] == ["a", "b", "c"]


def test_recent_events_are_capped_and_the_omission_is_noted() -> None:
    events = [
        make_event(f"e{index:02d}", occurred_at=NOW - timedelta(minutes=index))
        for index in range(30)
    ]

    context = build_brief_context(events, NOW, max_recent_events=10)

    assert len(context.recent_events) == 10
    # Newest first: the smallest minute offsets survive the cap.
    assert [digest.id for digest in context.recent_events] == [
        f"e{index:02d}" for index in range(10)
    ]
    assert context.event_count == 30
    assert any("Showing the 10 most recent of 30 events" in note for note in context.notes)


def test_default_recent_events_cap_is_applied() -> None:
    events = [
        make_event(f"e{index:03d}", occurred_at=NOW - timedelta(minutes=index))
        for index in range(DEFAULT_RECENT_EVENTS + 5)
    ]

    context = build_brief_context(events, NOW)

    assert len(context.recent_events) == DEFAULT_RECENT_EVENTS


def test_a_non_positive_cap_is_refused() -> None:
    try:
        build_brief_context([], NOW, max_recent_events=0)
    except ValueError as error:
        assert "max_recent_events" in str(error)
    else:  # pragma: no cover - the call must raise
        raise AssertionError("expected ValueError for a non-positive cap")


def test_building_does_not_mutate_the_events() -> None:
    events = [make_event("a"), make_event("b")]
    before = list(events)

    build_brief_context(events, NOW)

    assert events == before
