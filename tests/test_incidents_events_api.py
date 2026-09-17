"""Tests for the incident event-linking endpoints."""

from typing import Any

from fastapi.testclient import TestClient


def seed_events(client: TestClient, count: int) -> list[str]:
    """Store ``count`` real events and return their service-assigned ids in order."""
    ids: list[str] = []
    for index in range(count):
        response = client.post(
            "/events",
            json={
                "source": "integrations",
                "event_type": "integration.failed",
                "subject": f"Ticketing webhook failed {index}",
                "occurred_at": "2026-07-29T09:30:00Z",
                "severity": "high",
                "status": "failed",
            },
        )
        assert response.status_code == 201
        ids.append(response.json()["id"])
    return ids


def declare(client: TestClient, event_ids: list[str] | None = None) -> dict[str, Any]:
    """Declare an incident over ``event_ids`` (seeding two real events by default)."""
    if event_ids is None:
        event_ids = seed_events(client, 2)
    payload: dict[str, Any] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": "high",
        "event_ids": event_ids,
    }
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
    base = seed_events(client, 2)
    extra = seed_events(client, 2)
    incident_id = declare(client, base)["id"]

    response = link(client, incident_id, event_ids=extra)

    assert response.status_code == 200
    assert response.json()["event_ids"] == base + extra


def test_linking_is_persisted(client: TestClient) -> None:
    base = seed_events(client, 2)
    [extra] = seed_events(client, 1)
    incident_id = declare(client, base)["id"]
    link(client, incident_id, event_ids=[extra])

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["event_ids"] == [*base, extra]


def test_linking_an_already_cited_event_is_idempotent(client: TestClient) -> None:
    base = seed_events(client, 2)
    [extra] = seed_events(client, 1)
    incident_id = declare(client, base)["id"]

    response = link(client, incident_id, event_ids=[base[1], extra])

    assert response.status_code == 200
    assert response.json()["event_ids"] == [*base, extra]


def test_linking_an_unknown_event_id_is_rejected(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = link(client, incident_id, event_ids=["not-a-stored-event"])

    assert response.status_code == 422
    assert "not-a-stored-event" in response.json()["detail"]


def test_linking_to_an_unknown_incident_is_a_404(client: TestClient) -> None:
    [event_id] = seed_events(client, 1)

    response = link(client, "missing", event_ids=[event_id])

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_linking_to_a_closed_incident_is_a_conflict(client: TestClient) -> None:
    incident_id = declare(client)["id"]
    client.post(f"/incidents/{incident_id}/transition", json={"status": "closed"})
    [event_id] = seed_events(client, 1)

    response = link(client, incident_id, event_ids=[event_id])

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
    [event_id] = seed_events(client, 1)

    response = link(client, incident_id, event_ids=[event_id], extra="x")

    assert response.status_code == 422


def test_unlinking_removes_an_event(client: TestClient) -> None:
    first, second, third = seed_events(client, 3)
    incident_id = declare(client, [first, second, third])["id"]

    response = unlink(client, incident_id, second)

    assert response.status_code == 200
    assert response.json()["event_ids"] == [first, third]


def test_unlinking_is_persisted(client: TestClient) -> None:
    first, second = seed_events(client, 2)
    incident_id = declare(client, [first, second])["id"]
    unlink(client, incident_id, second)

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["event_ids"] == [first]


def test_unlinking_an_uncited_event_is_idempotent(client: TestClient) -> None:
    base = seed_events(client, 2)
    incident_id = declare(client, base)["id"]

    response = unlink(client, incident_id, "e99")

    assert response.status_code == 200
    assert response.json()["event_ids"] == base


def test_unlinking_to_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = unlink(client, "missing", "e17")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_unlinking_the_last_event_is_a_conflict(client: TestClient) -> None:
    [event_id] = seed_events(client, 1)
    incident_id = declare(client, [event_id])["id"]

    response = unlink(client, incident_id, event_id)

    assert response.status_code == 409


def test_unlinking_from_a_closed_incident_is_a_conflict(client: TestClient) -> None:
    first, second = seed_events(client, 2)
    incident_id = declare(client, [first, second])["id"]
    client.post(f"/incidents/{incident_id}/transition", json={"status": "closed"})

    response = unlink(client, incident_id, first)

    assert response.status_code == 409
    assert "closed" in response.json()["detail"]
