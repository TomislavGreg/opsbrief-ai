"""Tests for the incident resolution endpoint."""

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


def test_resolving_moves_the_incident_and_records_the_note(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = client.post(
        f"/incidents/{incident_id}/resolution",
        json={"note": "Restarted the ticketing sync and confirmed recovery."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["resolution_note"] == "Restarted the ticketing sync and confirmed recovery."


def test_a_resolved_incident_reads_back_with_its_note(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    client.post(f"/incidents/{incident_id}/resolution", json={"note": "Cleared the backlog."})

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["resolution_note"] == "Cleared the backlog."


def test_the_note_is_optional(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = client.post(f"/incidents/{incident_id}/resolution", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "resolved"
    assert body["resolution_note"] is None


def test_resolving_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = client.post("/incidents/missing/resolution", json={"note": "x"})

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_resolving_an_already_resolved_incident_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    client.post(f"/incidents/{incident_id}/resolution", json={"note": "Fixed."})

    response = client.post(f"/incidents/{incident_id}/resolution", json={"note": "Again."})

    assert response.status_code == 409
    assert "resolved" in response.json()["detail"]


def test_an_unknown_field_in_the_body_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = client.post(f"/incidents/{incident_id}/resolution", json={"status": "closed"})

    assert response.status_code == 422


def test_an_over_long_note_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = client.post(f"/incidents/{incident_id}/resolution", json={"note": "x" * 2_001})

    assert response.status_code == 422
