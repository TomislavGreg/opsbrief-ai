"""Tests for the event ingestion endpoint."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from opsbrief.storage import EventStore


def submission(**overrides: Any) -> dict[str, Any]:
    """Return a valid submission payload, with ``overrides`` applied."""
    payload: dict[str, Any] = {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is one short",
        "occurred_at": "2026-07-29T09:30:00Z",
    }
    payload.update(overrides)
    return payload


def test_accepted_event_is_created(client: TestClient) -> None:
    response = client.post("/events", json=submission())

    assert response.status_code == 201
    body = response.json()
    assert body["source"] == "rostering"
    assert body["event_type"] == "shift.unfilled"
    assert body["subject"] == "Steward shift for fixture 4821 is one short"


def test_accepted_event_is_given_an_identity(client: TestClient) -> None:
    body = client.post("/events", json=submission()).json()

    assert body["id"]
    assert body["received_at"]


def test_optional_fields_default_when_omitted(client: TestClient) -> None:
    body = client.post("/events", json=submission()).json()

    assert body["severity"] == "info"
    assert body["status"] is None
    assert body["entity_type"] is None
    assert body["entity_id"] is None
    assert body["due_at"] is None
    assert body["external_id"] is None
    assert body["metadata"] == {}


def test_optional_fields_are_kept(client: TestClient) -> None:
    body = client.post(
        "/events",
        json=submission(
            severity="high",
            status="open",
            entity_type="fixture",
            entity_id="4821",
            due_at="2026-07-29T18:00:00Z",
            external_id="roster-9931",
        ),
    ).json()

    assert body["severity"] == "high"
    assert body["status"] == "open"
    assert body["entity_type"] == "fixture"
    assert body["entity_id"] == "4821"
    assert body["due_at"] == "2026-07-29T18:00:00Z"
    assert body["external_id"] == "roster-9931"


def test_metadata_keeps_the_types_it_arrived_as(client: TestClient) -> None:
    metadata = {"venue": "North Stand", "required": 4, "ratio": 0.75, "urgent": True, "note": None}

    body = client.post("/events", json=submission(metadata=metadata)).json()

    assert body["metadata"] == metadata


def test_offset_timestamps_are_reported_as_utc(client: TestClient) -> None:
    body = client.post("/events", json=submission(occurred_at="2026-07-29T11:30:00+02:00")).json()

    assert body["occurred_at"] == "2026-07-29T09:30:00Z"


def test_accepted_event_is_stored(client: TestClient, store: EventStore) -> None:
    body = client.post("/events", json=submission()).json()

    stored = store.get(body["id"])
    assert stored is not None
    assert stored.subject == body["subject"]
    assert store.count() == 1


def test_each_submission_is_stored_separately(client: TestClient, store: EventStore) -> None:
    first = client.post("/events", json=submission()).json()
    second = client.post("/events", json=submission()).json()

    assert first["id"] != second["id"]
    assert store.count() == 2


@pytest.mark.parametrize(
    ("description", "payload"),
    [
        ("missing source", {k: v for k, v in submission().items() if k != "source"}),
        ("blank subject", submission(subject="")),
        ("naive occurred_at", submission(occurred_at="2026-07-29T09:30:00")),
        ("uppercase event_type", submission(event_type="Shift.Unfilled")),
        ("unknown field", submission(priority="urgent")),
        ("entity_type without entity_id", submission(entity_type="fixture")),
        ("nested metadata", submission(metadata={"venue": {"name": "North Stand"}})),
        ("unknown severity", submission(severity="catastrophic")),
        ("unknown status", submission(status="pending")),
    ],
)
def test_invalid_submissions_are_rejected(
    client: TestClient, store: EventStore, description: str, payload: dict[str, Any]
) -> None:
    response = client.post("/events", json=payload)

    assert response.status_code == 422, description
    assert store.count() == 0, f"{description} must not be stored"


def test_endpoint_is_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "post" in paths["/events"]


def test_batch_stores_every_event(client: TestClient, store: EventStore) -> None:
    payload = {"events": [submission(subject=f"Event {index}") for index in range(3)]}

    response = client.post("/events/batch", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["count"] == 3
    assert [event["subject"] for event in body["events"]] == [
        "Event 0",
        "Event 1",
        "Event 2",
    ]
    assert store.count() == 3


def test_batch_events_are_given_distinct_identities(client: TestClient) -> None:
    payload = {"events": [submission(), submission()]}

    body = client.post("/events/batch", json=payload).json()

    identities = [event["id"] for event in body["events"]]
    assert all(identities)
    assert len(set(identities)) == 2


def test_empty_batch_is_rejected(client: TestClient, store: EventStore) -> None:
    response = client.post("/events/batch", json={"events": []})

    assert response.status_code == 422
    assert store.count() == 0


def test_batch_with_an_invalid_event_stores_nothing(client: TestClient, store: EventStore) -> None:
    payload = {"events": [submission(), submission(subject="")]}

    response = client.post("/events/batch", json=payload)

    assert response.status_code == 422
    assert store.count() == 0


def test_batch_rejects_unknown_wrapper_fields(client: TestClient, store: EventStore) -> None:
    payload = {"events": [submission()], "priority": "urgent"}

    response = client.post("/events/batch", json=payload)

    assert response.status_code == 422
    assert store.count() == 0


def test_batch_endpoint_is_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "post" in paths["/events/batch"]


def test_listing_an_empty_store_returns_an_empty_page(client: TestClient) -> None:
    body = client.get("/events").json()

    assert body == {"total": 0, "limit": 50, "offset": 0, "events": []}


def test_listing_returns_stored_events_newest_first(client: TestClient) -> None:
    client.post("/events", json=submission(subject="Older", occurred_at="2026-07-29T08:00:00Z"))
    client.post("/events", json=submission(subject="Newer", occurred_at="2026-07-29T10:00:00Z"))

    body = client.get("/events").json()

    assert body["total"] == 2
    assert [event["subject"] for event in body["events"]] == ["Newer", "Older"]


def test_listing_filters_by_source_and_severity(client: TestClient) -> None:
    client.post("/events", json=submission(source="integrations", severity="high"))
    client.post("/events", json=submission(source="integrations", severity="low"))
    client.post("/events", json=submission(source="rostering", severity="high"))

    body = client.get("/events", params={"source": "integrations", "severity": "high"}).json()

    assert body["total"] == 1
    assert body["events"][0]["source"] == "integrations"
    assert body["events"][0]["severity"] == "high"


def test_listing_reports_the_total_beyond_the_page(client: TestClient) -> None:
    for hour in range(5):
        client.post("/events", json=submission(occurred_at=f"2026-07-29T0{hour}:00:00Z"))

    body = client.get("/events", params={"limit": 2, "offset": 0}).json()

    assert body["total"] == 5
    assert body["limit"] == 2
    assert len(body["events"]) == 2


def test_listing_pages_do_not_overlap(client: TestClient) -> None:
    for hour in range(4):
        client.post("/events", json=submission(occurred_at=f"2026-07-29T0{hour}:00:00Z"))

    first = client.get("/events", params={"limit": 2, "offset": 0}).json()["events"]
    second = client.get("/events", params={"limit": 2, "offset": 2}).json()["events"]

    ids = [event["id"] for event in first + second]
    assert len(set(ids)) == 4


@pytest.mark.parametrize(
    ("description", "params"),
    [
        ("limit below one", {"limit": 0}),
        ("limit above the maximum", {"limit": 10_000}),
        ("negative offset", {"offset": -1}),
        ("unknown severity", {"severity": "catastrophic"}),
        ("unknown status", {"status": "pending"}),
        ("unknown query parameter", {"unexpected": "value"}),
    ],
)
def test_listing_rejects_invalid_query_parameters(
    client: TestClient, description: str, params: dict[str, Any]
) -> None:
    response = client.get("/events", params=params)

    assert response.status_code == 422, description


def test_listing_endpoint_is_documented(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "get" in paths["/events"]
