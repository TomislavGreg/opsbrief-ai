"""Tests for the synthetic operational-event fixtures."""

from datetime import UTC

from fastapi.testclient import TestClient

from opsbrief.events import Event, EventInput
from opsbrief.samples import (
    load_sample_events,
    load_sample_match_events,
    load_sample_match_stored_events,
)


def test_load_returns_validated_event_inputs() -> None:
    events = load_sample_events()

    assert len(events) > 1
    assert all(isinstance(event, EventInput) for event in events)


def test_timestamps_are_timezone_aware_utc() -> None:
    for event in load_sample_events():
        assert event.occurred_at.tzinfo is not None
        assert event.occurred_at.utcoffset() == UTC.utcoffset(None)
        if event.due_at is not None:
            assert event.due_at.utcoffset() == UTC.utcoffset(None)


def test_external_ids_are_unique_per_source() -> None:
    keys = [
        (event.source, event.external_id)
        for event in load_sample_events()
        if event.external_id is not None
    ]

    assert len(keys) == len(set(keys))


def test_fixtures_cover_several_sources() -> None:
    sources = {event.source for event in load_sample_events()}

    assert {"rostering", "tasks", "integrations", "quality"} <= sources


def test_repeated_integration_failure_is_present() -> None:
    failures = [
        event
        for event in load_sample_events()
        if event.event_type == "integration.failed" and event.entity_id == "ticketing-webhook"
    ]

    assert len(failures) >= 3


def test_fixtures_ingest_through_the_batch_endpoint(client: TestClient) -> None:
    events = load_sample_events()

    response = client.post(
        "/events/batch",
        json={"events": [event.model_dump(mode="json") for event in events]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["count"] == len(events)
    assert len(body["events"]) == len(events)
    assert all(stored["id"] for stored in body["events"])


def test_match_stored_events_are_stored_event_records() -> None:
    stored = load_sample_match_stored_events()
    inputs = load_sample_match_events()

    assert len(stored) == len(inputs)
    assert all(isinstance(event, Event) for event in stored)


def test_match_stored_event_ids_come_from_the_external_ids() -> None:
    stored = load_sample_match_stored_events()

    for event, source in zip(stored, load_sample_match_events(), strict=True):
        assert event.id == source.external_id
        assert event.received_at == event.occurred_at


def test_match_stored_events_have_unique_stable_ids() -> None:
    first = load_sample_match_stored_events()
    second = load_sample_match_stored_events()

    ids = [event.id for event in first]
    assert len(ids) == len(set(ids))
    # Reproducible: the same fixture always resolves to the same ids.
    assert ids == [event.id for event in second]


def test_match_load_returns_validated_event_inputs() -> None:
    events = load_sample_match_events()

    assert len(events) > 1
    assert all(isinstance(event, EventInput) for event in events)


def test_match_timestamps_are_timezone_aware() -> None:
    for event in load_sample_match_events():
        assert event.occurred_at.tzinfo is not None
        assert event.occurred_at.utcoffset() is not None
        if event.due_at is not None:
            assert event.due_at.utcoffset() is not None


def test_match_external_ids_are_unique_per_source() -> None:
    keys = [
        (event.source, event.external_id)
        for event in load_sample_match_events()
        if event.external_id is not None
    ]

    assert len(keys) == len(set(keys))


def test_match_fixtures_cover_the_match_operations_sources() -> None:
    sources = {event.source for event in load_sample_match_events()}

    assert {"rostering", "tasks", "integrations", "quality", "facilities"} <= sources


def test_match_fixtures_exercise_the_risk_rules() -> None:
    events = load_sample_match_events()

    assert any(event.status == "overdue" for event in events)
    assert any(event.status == "blocked" for event in events)

    broadcast_failures = [
        event
        for event in events
        if event.event_type == "integration.failed" and event.entity_id == "broadcast-feed"
    ]
    assert len(broadcast_failures) >= 3


def test_match_fixtures_are_distinct_from_the_general_set() -> None:
    general_ids = {event.external_id for event in load_sample_events()}
    match_ids = {event.external_id for event in load_sample_match_events()}

    assert general_ids.isdisjoint(match_ids)


def test_match_fixtures_ingest_through_the_batch_endpoint(client: TestClient) -> None:
    events = load_sample_match_events()

    response = client.post(
        "/events/batch",
        json={"events": [event.model_dump(mode="json") for event in events]},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["count"] == len(events)
    assert len(body["events"]) == len(events)
    assert all(stored["id"] for stored in body["events"])
