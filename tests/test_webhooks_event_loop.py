"""Event-loop regression test for webhook ingestion (AI-100).

The webhook authenticates a delivery and then does blocking work: HMAC
verification, JSON parsing and a SQLite write. Before AI-100 that work ran
directly in the async handler, so a slow persistence step held the event loop and
stalled every other request the loop was serving. The handler now dispatches the
blocking work to a worker thread, so the loop stays free.

This test proves that. It holds the webhook inside a paused persistence step and
then measures how quickly the event loop can resume an independent awaiting
coroutine and serve a lightweight ``GET /health``. If the blocking work ran on the
loop, neither could make progress until the pause ended; with it off the loop,
both are prompt. The pause releases itself on a timer thread, so a regression is
detected as a slow response rather than hanging the suite.
"""

import asyncio
import json
import threading
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport

from opsbrief.api.dependencies import get_event_store
from opsbrief.config import get_settings
from opsbrief.events import Event
from opsbrief.main import create_app
from opsbrief.webhooks import SIGNATURE_HEADER, TIMESTAMP_HEADER, compute_signature

SECRET = "a-sufficiently-long-shared-secret"
# How long persistence stays paused. Long enough that a loop stalled for this
# whole span is unmistakable, short enough to keep the test quick.
BLOCK_SECONDS = 1.0
# A free loop resumes an awaiting coroutine and serves /health in milliseconds; a
# stalled one cannot until the pause releases. This threshold sits well between.
RESPONSIVE_THRESHOLD = 0.5
# A safety net so the worker thread never waits forever if the timer is missed.
SAFETY_TIMEOUT = 10.0


class PausingEventStore:
    """A stand-in event store whose write pauses for a fixed span.

    ``add_all_or_get`` signals that it has been entered, schedules its own release
    on a timer thread (so the pause ends regardless of what the event loop is doing)
    and waits for that release. It returns the events unchanged, which
    ``record_events`` reads as every event newly stored.
    """

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def add_all_or_get(self, events: list[Event]) -> list[Event]:
        threading.Timer(BLOCK_SECONDS, self.release.set).start()
        self.entered.set()
        self.release.wait(timeout=SAFETY_TIMEOUT)
        return events


@pytest.fixture
def app_and_store(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Any, PausingEventStore]]:
    """Return an app with the webhook enabled and a pausing store injected."""
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPSBRIEF_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    app = create_app()
    store = PausingEventStore()
    app.dependency_overrides[get_event_store] = lambda: store
    try:
        yield app, store
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def _signed_headers(body: bytes) -> dict[str, str]:
    stamp = str(int(time.time()))
    return {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: stamp,
        SIGNATURE_HEADER: compute_signature(SECRET, stamp, body),
    }


def test_paused_persistence_does_not_stall_the_event_loop(
    app_and_store: tuple[Any, PausingEventStore],
) -> None:
    app, store = app_and_store
    body = json.dumps(
        {
            "events": [
                {
                    "source": "rostering",
                    "event_type": "shift.unfilled",
                    "subject": "Steward shift for fixture 4821 is one short",
                    "occurred_at": "2026-07-29T09:30:00Z",
                    "external_id": "roster-9931",
                }
            ]
        }
    ).encode("utf-8")

    async def scenario() -> None:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            started = time.monotonic()
            webhook = asyncio.create_task(
                client.post("/webhooks/events", content=body, headers=_signed_headers(body))
            )

            # Wait, on a worker thread, until the webhook has reached the paused
            # persistence step. The worker sees ``entered`` at once, but the event
            # loop can only resume this coroutine if it is free. If the webhook were
            # blocking the loop, this would not return until the pause released.
            await asyncio.to_thread(store.entered.wait, SAFETY_TIMEOUT)
            resume_latency = time.monotonic() - started
            assert store.entered.is_set()
            assert resume_latency < RESPONSIVE_THRESHOLD

            # And the loop can still serve an independent request while persistence
            # is paused, rather than only once the pause ends.
            assert not store.release.is_set()
            health = await client.get("/health")
            assert health.status_code == 200
            assert not store.release.is_set()

            # The pause releases on its timer; the webhook then commits and returns.
            response = await webhook
            assert response.status_code == 202
            assert response.json()["count"] == 1

    asyncio.run(scenario())
