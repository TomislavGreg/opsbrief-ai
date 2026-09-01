"""Tests for the incident-timeline endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

NOW = datetime.now(UTC).replace(microsecond=0)


def submission(**overrides: Any) -> dict[str, Any]:
    """Return a valid event submission payload, with ``overrides`` applied."""
    payload: dict[str, Any] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": "Ticketing webhook failed",
        "occurred_at": (NOW - timedelta(hours=2)).isoformat(),
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    return payload


def post_event(client: TestClient, **overrides: Any) -> str:
    """Submit an event and return the identifier it was stored under."""
    response = client.post("/events", json=submission(**overrides))
    assert response.status_code == 201
    return response.json()["id"]


def declare_incident(client: TestClient, event_ids: list[str], **overrides: Any) -> str:
    """Declare an incident over ``event_ids`` and return its identifier."""
    payload: dict[str, Any] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": "high",
        "event_ids": event_ids,
    }
    payload.update(overrides)
    response = client.post("/incidents", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def test_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = client.get("/incidents/missing/timeline")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_timeline_lays_cited_events_out_oldest_first(client: TestClient) -> None:
    later = post_event(client, occurred_at=(NOW - timedelta(hours=1)).isoformat())
    earlier = post_event(client, occurred_at=(NOW - timedelta(hours=3)).isoformat())
    # Cite the events out of chronological order; the timeline reorders them.
    incident_id = declare_incident(client, [later, earlier])

    response = client.get(f"/incidents/{incident_id}/timeline")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == incident_id
    assert [entry["id"] for entry in body["entries"]] == [earlier, later]
    assert body["missing_event_ids"] == []
    assert body["started_at"] is not None
    assert body["ended_at"] is not None
    # The entry carries the fields a timeline describes an event with, not metadata.
    assert set(body["entries"][0]) == {
        "id",
        "source",
        "event_type",
        "subject",
        "occurred_at",
        "severity",
        "status",
    }


def test_a_cited_event_with_no_stored_record_is_reported_missing(client: TestClient) -> None:
    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id, "gone"])

    body = client.get(f"/incidents/{incident_id}/timeline").json()

    assert [entry["id"] for entry in body["entries"]] == [event_id]
    assert body["missing_event_ids"] == ["gone"]


def test_an_incident_whose_events_are_all_missing_has_an_empty_span(client: TestClient) -> None:
    incident_id = declare_incident(client, ["gone"])

    body = client.get(f"/incidents/{incident_id}/timeline").json()

    assert body["entries"] == []
    assert body["missing_event_ids"] == ["gone"]
    assert body["started_at"] is None
    assert body["ended_at"] is None
