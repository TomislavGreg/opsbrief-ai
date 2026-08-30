"""Tests for seeding demo data on application startup."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from opsbrief.config import get_settings
from opsbrief.main import create_app
from opsbrief.samples import build_sample_qc_incident, load_sample_match_stored_events


@pytest.fixture
def demo_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Return a client for an application started with demo-data mode on."""
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPSBRIEF_DEMO_DATA", "true")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()


def test_demo_mode_seeds_events_on_startup(demo_client: TestClient) -> None:
    response = demo_client.get("/events")

    assert response.status_code == 200
    assert response.json()["total"] == len(load_sample_match_stored_events())


def test_demo_mode_seeds_an_incident_on_startup(demo_client: TestClient) -> None:
    response = demo_client.get(f"/incidents/{build_sample_qc_incident().id}")

    assert response.status_code == 200
    assert response.json()["status"] == "resolved"


def test_the_store_is_empty_without_demo_mode(client: TestClient) -> None:
    response = client.get("/events")

    assert response.status_code == 200
    assert response.json()["total"] == 0
