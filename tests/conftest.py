"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from opsbrief.config import get_settings
from opsbrief.main import create_app
from opsbrief.storage import EventStore


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Return a test client bound to an application backed by a throwaway database.

    The client is used as a context manager so that the application lifespan
    runs and the event store is opened, as it is when the service is served.
    """
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def store(client: TestClient) -> EventStore:
    """Return the event store the test client's application is writing to."""
    return client.app.state.event_store
