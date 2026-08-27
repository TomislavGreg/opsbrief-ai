"""Tests for the server-rendered dashboard endpoint."""

from fastapi.testclient import TestClient

from opsbrief import __version__


def test_dashboard_returns_html(client: TestClient) -> None:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.text.lstrip().startswith("<!DOCTYPE html>")


def test_dashboard_shows_service_identity(client: TestClient) -> None:
    body = client.get("/dashboard").text

    assert "OpsBrief AI" in body
    assert __version__ in body


def test_dashboard_links_into_the_read_endpoints(client: TestClient) -> None:
    body = client.get("/dashboard").text

    for href in ('href="/brief"', 'href="/risks"', 'href="/events"', 'href="/incidents"'):
        assert href in body


def test_dashboard_renders_without_any_stored_events(client: TestClient) -> None:
    # The shell reads the settings, not the store, so it renders on an empty
    # database exactly as it would with events recorded.
    response = client.get("/dashboard")

    assert response.status_code == 200


def test_dashboard_is_in_the_openapi_schema(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    assert "/dashboard" in paths
