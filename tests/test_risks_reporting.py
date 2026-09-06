"""Tests for the risk-reporting service."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from opsbrief.events import Event, EventInput, EventStatus
from opsbrief.risks import RiskQuery, RiskSeverity
from opsbrief.services import list_risks
from opsbrief.storage import EventStore

NOW = datetime(2026, 8, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def store() -> Iterator[EventStore]:
    """Return a throwaway in-memory event store."""
    with EventStore.open("sqlite:///:memory:") as opened:
        yield opened


def add_event(store: EventStore, event_id: str, **overrides: object) -> Event:
    """Build a stored event with the given id and fields, and add it to ``store``."""
    payload: dict[str, object] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": f"Work item {event_id}",
        "occurred_at": NOW - timedelta(hours=6),
    }
    payload.update(overrides)
    event = Event.from_input(EventInput(**payload)).model_copy(update={"id": event_id})
    return store.add(event)


def test_no_events_yields_no_risks(store: EventStore) -> None:
    snapshot = list_risks(store, NOW)

    assert snapshot.total == 0
    assert snapshot.risks == []
    assert snapshot.generated_at == NOW


def test_snapshot_records_the_reference_instant(store: EventStore) -> None:
    add_event(store, "e1", due_at=NOW - timedelta(hours=2))

    assert list_risks(store, NOW).generated_at == NOW


def test_overdue_event_becomes_a_traceable_risk(store: EventStore) -> None:
    add_event(store, "late", due_at=NOW - timedelta(hours=2))

    snapshot = list_risks(store, NOW)

    assert snapshot.total == 1
    assert snapshot.risks[0].rule == "overdue_work"
    assert snapshot.risks[0].event_ids == ["late"]


def test_benign_events_raise_nothing(store: EventStore) -> None:
    add_event(store, "ok", due_at=NOW + timedelta(days=1))
    add_event(store, "done", due_at=NOW - timedelta(days=1), status=EventStatus.RESOLVED)

    assert list_risks(store, NOW).risks == []


def test_risks_from_different_rules_are_ranked_by_priority(store: EventStore) -> None:
    # Blocked work long enough to be high; overdue work only recently, so medium.
    add_event(store, "blocked", status=EventStatus.BLOCKED, occurred_at=NOW - timedelta(days=2))
    add_event(store, "overdue", due_at=NOW - timedelta(hours=1))

    snapshot = list_risks(store, NOW)

    severities = [risk.severity for risk in snapshot.risks]
    assert severities == sorted(severities, key=lambda s: -{"medium": 2, "high": 3}[s.value])
    assert snapshot.risks[0].severity is RiskSeverity.HIGH
    assert snapshot.risks[0].event_ids == ["blocked"]


def test_reads_do_not_mutate_the_store(store: EventStore) -> None:
    add_event(store, "late", due_at=NOW - timedelta(hours=2))

    list_risks(store, NOW)

    assert store.count() == 1


def _two_rule_store(store: EventStore) -> None:
    """Seed a store with one high blocked risk and one medium overdue risk."""
    add_event(store, "blocked", status=EventStatus.BLOCKED, occurred_at=NOW - timedelta(days=2))
    add_event(store, "overdue", due_at=NOW - timedelta(hours=1))


def test_an_empty_query_returns_the_whole_picture(store: EventStore) -> None:
    _two_rule_store(store)

    unfiltered = list_risks(store, NOW)
    with_empty_query = list_risks(store, NOW, RiskQuery())

    assert with_empty_query.model_dump() == unfiltered.model_dump()
    assert with_empty_query.total == 2


def test_severity_filter_keeps_only_matching_risks(store: EventStore) -> None:
    _two_rule_store(store)

    snapshot = list_risks(store, NOW, RiskQuery(severity=RiskSeverity.HIGH))

    assert snapshot.total == 1
    assert snapshot.risks[0].event_ids == ["blocked"]
    assert snapshot.generated_at == NOW


def test_rule_filter_keeps_only_that_rule(store: EventStore) -> None:
    _two_rule_store(store)

    snapshot = list_risks(store, NOW, RiskQuery(rule="overdue_work"))

    assert snapshot.total == 1
    assert snapshot.risks[0].rule == "overdue_work"
    assert snapshot.risks[0].event_ids == ["overdue"]


def test_filters_preserve_priority_order(store: EventStore) -> None:
    # Two high-severity risks from different rules; the filter keeps ranking intact.
    add_event(store, "blocked", status=EventStatus.BLOCKED, occurred_at=NOW - timedelta(days=2))
    add_event(store, "overdue", due_at=NOW - timedelta(days=2))

    unfiltered = list_risks(store, NOW)
    filtered = list_risks(store, NOW, RiskQuery(severity=RiskSeverity.HIGH))

    assert [risk.severity for risk in filtered.risks] == [RiskSeverity.HIGH, RiskSeverity.HIGH]
    # Same risks, same order as the unfiltered snapshot: filtering does not reorder.
    assert [risk.event_ids for risk in filtered.risks] == [
        risk.event_ids for risk in unfiltered.risks
    ]


def test_a_filter_matching_nothing_yields_an_empty_snapshot(store: EventStore) -> None:
    _two_rule_store(store)

    snapshot = list_risks(store, NOW, RiskQuery(severity=RiskSeverity.CRITICAL))

    assert snapshot.total == 0
    assert snapshot.risks == []
    # The snapshot is still dated, so an empty result reads as "nothing matched now".
    assert snapshot.generated_at == NOW
