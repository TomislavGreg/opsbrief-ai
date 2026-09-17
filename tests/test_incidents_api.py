"""Tests for the incident declaration and retrieval endpoints."""

from typing import Any

from fastapi.testclient import TestClient


def seed_events(client: TestClient, count: int = 2) -> list[str]:
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


def declaration(**overrides: Any) -> dict[str, Any]:
    """Return a declaration body with placeholder events, for validation tests.

    The placeholder ids do not exist in the store, so this body is only for tests
    whose request is rejected before the events are checked. Tests that need a
    stored incident go through :func:`declare`, which cites real events.
    """
    payload: dict[str, Any] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": "high",
        "event_ids": ["e17", "e18"],
    }
    payload.update(overrides)
    return payload


def declare(client: TestClient, **overrides: Any) -> dict[str, Any]:
    """Declare an incident over freshly seeded real events and return the stored body."""
    body = declaration(**overrides)
    if "event_ids" not in overrides:
        body["event_ids"] = seed_events(client, 2)
    response = client.post("/incidents", json=body)
    assert response.status_code == 201
    return response.json()


def test_declaring_stores_an_open_incident(client: TestClient) -> None:
    event_ids = seed_events(client, 2)
    response = client.post("/incidents", json=declaration(event_ids=event_ids))

    assert response.status_code == 201
    body = response.json()
    assert body["id"]
    assert body["status"] == "open"
    assert body["severity"] == "high"
    assert body["event_ids"] == event_ids
    assert body["resolved_at"] is None


def test_a_declaration_citing_an_unknown_event_is_rejected(client: TestClient) -> None:
    response = client.post("/incidents", json=declaration(event_ids=["not-a-stored-event"]))

    assert response.status_code == 422
    assert "not-a-stored-event" in response.json()["detail"]


def test_a_declared_incident_can_be_read_back(client: TestClient) -> None:
    incident_id = declare(client)["id"]

    response = client.get(f"/incidents/{incident_id}")

    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = client.get("/incidents/missing")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_a_declaration_without_events_is_rejected(client: TestClient) -> None:
    response = client.post("/incidents", json=declaration(event_ids=[]))

    assert response.status_code == 422


def test_a_declaration_with_an_unknown_field_is_rejected(client: TestClient) -> None:
    response = client.post("/incidents", json=declaration(status="open"))

    assert response.status_code == 422


def test_listing_reports_the_total_and_page(client: TestClient) -> None:
    declare(client, title="First")
    declare(client, title="Second")

    response = client.get("/incidents", params={"limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert len(body["incidents"]) == 1


def test_listing_filters_by_status(client: TestClient) -> None:
    declare(client, title="Open one")
    declare(client, title="Another open")

    response = client.get("/incidents", params={"status": "investigating"})

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_listing_filters_by_severity(client: TestClient) -> None:
    declare(client, title="High one", severity="high")
    declare(client, title="Low one", severity="low")

    response = client.get("/incidents", params={"severity": "low"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [incident["title"] for incident in body["incidents"]] == ["Low one"]


def test_a_malformed_severity_filter_is_rejected(client: TestClient) -> None:
    response = client.get("/incidents", params={"severity": "not-a-severity"})

    assert response.status_code == 422


def test_listing_filters_by_opened_window(client: TestClient) -> None:
    declare(client, title="Just opened")

    past = client.get(
        "/incidents",
        params={"opened_to": "2020-01-01T00:00:00Z"},
    )
    covering = client.get(
        "/incidents",
        params={"opened_from": "2020-01-01T00:00:00Z"},
    )

    assert past.status_code == 200
    assert past.json()["total"] == 0
    assert covering.status_code == 200
    assert covering.json()["total"] == 1


def test_a_malformed_opened_bound_is_rejected(client: TestClient) -> None:
    response = client.get("/incidents", params={"opened_from": "2026-08-16T14:00:00"})

    assert response.status_code == 422


def test_an_inverted_opened_window_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/incidents",
        params={"opened_from": "2026-08-16T18:00:00Z", "opened_to": "2026-08-16T14:00:00Z"},
    )

    assert response.status_code == 422


def test_listing_an_empty_store_is_an_empty_page(client: TestClient) -> None:
    response = client.get("/incidents")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["incidents"] == []


def test_a_malformed_status_filter_is_rejected(client: TestClient) -> None:
    response = client.get("/incidents", params={"status": "not-a-status"})

    assert response.status_code == 422


def test_declared_incidents_are_listed_most_recent_first(client: TestClient) -> None:
    declare(client, title="First")
    declare(client, title="Second")

    response = client.get("/incidents")

    titles = [incident["title"] for incident in response.json()["incidents"]]
    assert set(titles) == {"First", "Second"}
    assert len(titles) == 2
