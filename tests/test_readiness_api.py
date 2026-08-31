"""Tests for the readiness endpoint."""

from fastapi.testclient import TestClient

from opsbrief.api.dependencies import get_incident_store
from opsbrief.storage import IncidentStore


def test_ready_when_the_stores_answer(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert [check["name"] for check in body["checks"]] == ["event_store", "incident_store"]
    assert all(check["ready"] for check in body["checks"])


def test_a_degraded_store_answers_503(client: TestClient) -> None:
    # A store that can no longer answer makes the service not ready: the endpoint
    # reports 503 with the failing dependency named, rather than a 200 or a 500.
    closed_store = IncidentStore.open("sqlite:///:memory:")
    closed_store.close()
    client.app.dependency_overrides[get_incident_store] = lambda: closed_store
    try:
        response = client.get("/health/ready")
    finally:
        client.app.dependency_overrides.pop(get_incident_store, None)

    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    incident_check = next(check for check in body["checks"] if check["name"] == "incident_store")
    assert incident_check["ready"] is False
    assert incident_check["detail"]


def test_readiness_is_listed_in_the_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/health/ready" in paths
