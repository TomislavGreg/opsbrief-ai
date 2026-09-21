"""Tests for application startup: configuration validation and store lifecycle."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from opsbrief import main as main_module
from opsbrief.config import get_settings
from opsbrief.main import create_app
from opsbrief.startup import ConfigurationError
from opsbrief.storage import EventStore, IncidentStore


def test_create_app_rejects_an_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    # An unknown provider fails at application build, not later on the first
    # /brief request, so a misconfiguration is caught before the service serves.
    monkeypatch.setenv("OPSBRIEF_AI_PROVIDER", "mystery")
    get_settings.cache_clear()
    try:
        with pytest.raises(ConfigurationError, match="mystery"):
            create_app()
    finally:
        get_settings.cache_clear()


def _raise_seed_failure(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("seeding failed")


def test_failed_seeding_closes_open_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    # If seeding fails after both stores are open, the lifespan's ExitStack closes
    # every already-open resource and leaves no partial state on the application.
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPSBRIEF_DEMO_DATA", "true")
    get_settings.cache_clear()

    opened: list[EventStore | IncidentStore] = []
    original_event_open = EventStore.open
    original_incident_open = IncidentStore.open

    def spy_event_open(url: str) -> EventStore:
        store = original_event_open(url)
        opened.append(store)
        return store

    def spy_incident_open(url: str) -> IncidentStore:
        store = original_incident_open(url)
        opened.append(store)
        return store

    monkeypatch.setattr(main_module.EventStore, "open", staticmethod(spy_event_open))
    monkeypatch.setattr(main_module.IncidentStore, "open", staticmethod(spy_incident_open))
    monkeypatch.setattr(main_module, "seed_demo_data", _raise_seed_failure)

    app = create_app()
    try:
        with pytest.raises(RuntimeError, match="seeding failed"), TestClient(app):
            pass
    finally:
        get_settings.cache_clear()

    assert len(opened) == 2
    # Both stores were closed on the way out, so a probe on either now raises.
    for store in opened:
        with pytest.raises(sqlite3.Error):
            store.ping()
    # No partial application state was left behind.
    assert getattr(app.state, "event_store", None) is None
    assert getattr(app.state, "incident_store", None) is None
