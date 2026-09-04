"""Tests for the incident event-linking endpoints."""

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


def link(client: TestClient, incident_id: str, **body: Any) -> Any:
    """Post an event-link request for an incident."""
    return client.post(f"/incidents/{incident_id}/events", json=body)


def unlink(client: TestClient, incident_id: str, event_id: str) -> Any:
    """Delete a linked event from an incident."""
    return client.delete(f"/incidents/{incident_id}/events/{event_id}")


def test_linking_appends_events(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = link(client, incident_id, event_ids=["e19", "e20"])

    assert response.status_code == 200
    assert response.json()["event_ids"] == ["e17", "e18", "e19", "e20"]


def test_linking_is_persisted(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    link(client, incident_id, event_ids=["e19"])

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["event_ids"] == ["e17", "e18", "e19"]


def test_linking_an_already_cited_event_is_idempotent(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = link(client, incident_id, event_ids=["e18", "e19"])

    assert response.status_code == 200
    assert response.json()["event_ids"] == ["e17", "e18", "e19"]


def test_linking_to_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = link(client, "missing", event_ids=["e19"])

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_linking_to_a_closed_incident_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    client.post(f"/incidents/{incident_id}/transition", json={"status": "closed"})

    response = link(client, incident_id, event_ids=["e19"])

    assert response.status_code == 409
    assert "closed" in response.json()["detail"]


def test_linking_an_empty_list_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = link(client, incident_id, event_ids=[])

    assert response.status_code == 422


def test_linking_a_blank_event_id_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = link(client, incident_id, event_ids=["  "])

    assert response.status_code == 422


def test_linking_an_unknown_field_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = link(client, incident_id, event_ids=["e19"], extra="x")

    assert response.status_code == 422


def test_unlinking_removes_an_event(client: TestClient) -> None:
    incident_id = declare(client, event_ids=["e17", "e18", "e19"])["id"]

    response = unlink(client, incident_id, "e18")

    assert response.status_code == 200
    assert response.json()["event_ids"] == ["e17", "e19"]


def test_unlinking_is_persisted(client: TestClient) -> None:
    incident_id = declare(client, event_ids=["e17", "e18"])["id"]
    unlink(client, incident_id, "e18")

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["event_ids"] == ["e17"]


def test_unlinking_an_uncited_event_is_idempotent(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = unlink(client, incident_id, "e99")

    assert response.status_code == 200
    assert response.json()["event_ids"] == ["e17", "e18"]


def test_unlinking_to_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = unlink(client, "missing", "e17")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_unlinking_the_last_event_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client, event_ids=["e17"])["id"]

    response = unlink(client, incident_id, "e17")

    assert response.status_code == 409


def test_unlinking_from_a_closed_incident_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client, event_ids=["e17", "e18"])["id"]
    client.post(f"/incidents/{incident_id}/transition", json={"status": "closed"})

    response = unlink(client, incident_id, "e17")

    assert response.status_code == 409
    assert "closed" in response.json()["detail"]
