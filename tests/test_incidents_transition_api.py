"""Tests for the incident lifecycle-transition endpoint."""

from typing import Any

from fastapi.testclient import TestClient


def declare(client: TestClient, **overrides: Any) -> dict[str, Any]:
    """Declare an incident and return the stored body."""
    payload: dict[str, Any] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": "high",
        "event_ids": ["e17", "e18"],
    }
    payload.update(overrides)
    response = client.post("/incidents", json=payload)
    assert response.status_code == 201
    return response.json()


def transition(client: TestClient, incident_id: str, **body: Any) -> Any:
    """Post a transition request for an incident."""
    return client.post(f"/incidents/{incident_id}/transition", json=body)


def test_moving_an_open_incident_to_investigating(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, status="investigating")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "investigating"
    assert body["is_active"] is True
    assert body["resolved_at"] is None


def test_a_transition_is_persisted(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    transition(client, incident_id, status="investigating")

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["status"] == "investigating"


def test_walking_through_the_active_states(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    assert transition(client, incident_id, status="investigating").status_code == 200
    monitoring = transition(client, incident_id, status="monitoring")

    assert monitoring.status_code == 200
    assert monitoring.json()["status"] == "monitoring"


def test_closing_records_the_note_and_the_resolution_instant(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, status="closed", note="Signed off after review.")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    assert body["is_terminal"] is True
    assert body["resolved_at"] is not None
    assert body["resolution_note"] == "Signed off after review."


def test_reopening_a_resolved_incident_clears_its_resolution(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    client.post(f"/incidents/{incident_id}/resolution", json={"note": "Thought it was fixed."})

    response = transition(client, incident_id, status="investigating")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "investigating"
    assert body["resolved_at"] is None
    assert body["resolution_note"] is None


def test_a_move_the_lifecycle_forbids_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    transition(client, incident_id, status="closed")

    response = transition(client, incident_id, status="investigating")

    assert response.status_code == 409
    assert "closed" in response.json()["detail"]


def test_repeating_the_current_state_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, status="open")

    assert response.status_code == 409


def test_transitioning_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = transition(client, "missing", status="investigating")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_a_note_on_a_reopening_move_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    client.post(f"/incidents/{incident_id}/resolution", json={})

    response = transition(client, incident_id, status="investigating", note="Back again.")

    assert response.status_code == 422


def test_a_missing_status_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, note="No target.")

    assert response.status_code == 422


def test_an_unknown_status_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, status="archived")

    assert response.status_code == 422


def test_an_unknown_field_in_the_body_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, status="investigating", extra="x")

    assert response.status_code == 422


def test_an_over_long_note_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = transition(client, incident_id, status="closed", note="x" * 2_001)

    assert response.status_code == 422
