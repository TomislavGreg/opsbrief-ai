"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from opsbrief import __version__


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_service_identity(client: TestClient) -> None:
    payload = client.get("/health").json()

    assert payload["service"] == "OpsBrief AI"
    assert payload["version"] == __version__
    assert payload["environment"]


def test_openapi_schema_is_available(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
