"""Tests for the request body size limiting middleware."""

import asyncio
import json
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from opsbrief.api import limits
from opsbrief.api.limits import MaxBodySizeMiddleware
from opsbrief.config import get_settings
from opsbrief.main import create_app


def build_app(max_bytes: int | None = None) -> FastAPI:
    """Return a tiny app that echoes the number of body bytes it managed to read."""
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_bytes=max_bytes)

    @app.post("/echo")
    async def echo(request: Request) -> dict[str, int]:
        body = await request.body()
        return {"read": len(body)}

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(build_app(max_bytes=1024)) as test_client:
        yield test_client


def test_a_body_under_the_limit_is_read_whole(client: TestClient) -> None:
    response = client.post("/echo", content=b"x" * 500)

    assert response.status_code == 200
    assert response.json()["read"] == 500


def test_a_body_exactly_at_the_limit_is_accepted(client: TestClient) -> None:
    response = client.post("/echo", content=b"x" * 1024)

    assert response.status_code == 200
    assert response.json()["read"] == 1024


def test_a_body_one_byte_over_the_limit_is_refused(client: TestClient) -> None:
    response = client.post("/echo", content=b"x" * 1025)

    assert response.status_code == 413
    assert "maximum size" in response.json()["detail"]


def test_an_excessive_declared_length_is_refused_before_reading(client: TestClient) -> None:
    # A large body carries a large Content-Length, so it is refused on the header
    # alone without the middleware needing to stream it.
    response = client.post("/echo", content=b"x" * (1024 * 64))

    assert response.status_code == 413


def test_a_streamed_body_without_content_length_is_bounded() -> None:
    # A generator body is sent chunked, with no Content-Length to check up front, so
    # the byte bound must still hold as the body streams rather than only on the
    # declared length.
    def body() -> Iterator[bytes]:
        for _ in range(100):
            yield b"x" * 256

    with TestClient(build_app(max_bytes=1024)) as client:
        response = client.post("/echo", content=body())

    assert response.status_code == 413


def test_receipt_stops_at_the_bound_plus_one_chunk() -> None:
    # Drive the middleware at the ASGI level so the count of delivered chunks is the
    # server-side receipt, not the client buffering the body. With no Content-Length,
    # receipt must stop at the bound plus at most the one chunk that crossed it.
    chunks_delivered = 0

    async def receive() -> dict[str, object]:
        nonlocal chunks_delivered
        chunks_delivered += 1
        return {"type": "http.request", "body": b"x" * 256, "more_body": True}

    sent: list[dict[str, object]] = []

    async def send(message: dict[str, object]) -> None:
        sent.append(message)

    async def drain_body(scope, inner_receive, inner_send):  # type: ignore[no-untyped-def]
        # A well-behaved handler reads the whole body first; drain it here so the
        # bound is what stops the read, not the handler giving up early.
        while True:
            message = await inner_receive()
            if not message.get("more_body", False):
                break

    middleware = MaxBodySizeMiddleware(drain_body, max_bytes=1024)
    scope = {"type": "http", "headers": []}
    asyncio.run(middleware(scope, receive, send))

    assert sent[0]["status"] == 413
    # 1024 // 256 == 4 chunks fill the bound; the 5th crosses it and stops receipt.
    assert chunks_delivered == 5


def test_a_streamed_body_under_the_limit_is_accepted() -> None:
    def body() -> Iterator[bytes]:
        for _ in range(4):
            yield b"x" * 256

    with TestClient(build_app(max_bytes=1024)) as client:
        response = client.post("/echo", content=body())

    assert response.status_code == 200
    assert response.json()["read"] == 1024


def test_the_module_default_bound_is_read_live(monkeypatch: pytest.MonkeyPatch) -> None:
    # An instance built without an explicit bound follows the module-level default,
    # read afresh per request, so adjusting it takes effect without a rebuild.
    monkeypatch.setattr(limits, "MAX_REQUEST_BODY_BYTES", 16)
    with TestClient(build_app()) as client:
        assert client.post("/echo", content=b"x" * 16).status_code == 200
        assert client.post("/echo", content=b"x" * 17).status_code == 413


def test_a_get_request_without_a_body_is_untouched(client: TestClient) -> None:
    # A route with no body still works: nothing to bound, nothing refused.
    app = build_app(max_bytes=1024)

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(app) as get_client:
        assert get_client.get("/ping").json() == {"ok": True}


def _make_app_client(monkeypatch: pytest.MonkeyPatch, max_bytes: int | None) -> TestClient:
    """Return a client for the real application, optionally with a lowered bound."""
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    if max_bytes is not None:
        monkeypatch.setattr(limits, "MAX_REQUEST_BODY_BYTES", max_bytes)
    get_settings.cache_clear()
    return TestClient(create_app())


def _valid_event() -> dict[str, object]:
    return {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is one short",
        "occurred_at": "2026-07-29T09:30:00Z",
    }


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/events", _valid_event()),
        ("/events/batch", {"events": [_valid_event()]}),
        ("/incidents", {"title": "Ticketing down", "severity": "high", "event_ids": ["e1"]}),
    ],
)
def test_the_byte_bound_covers_the_write_paths(
    monkeypatch: pytest.MonkeyPatch, path: str, payload: dict[str, object]
) -> None:
    # The same byte policy applies to the ordinary event, batch and incident write
    # paths, not only the webhook, and a body over the bound is refused with 413
    # before it is parsed, so nothing is stored.
    with _make_app_client(monkeypatch, max_bytes=16) as client:
        response = client.post(
            path,
            content=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 413
        assert client.get("/events").json()["total"] == 0
        assert client.get("/incidents").json()["total"] == 0
    get_settings.cache_clear()


def test_a_write_within_the_bound_still_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    # Under the ordinary bound a valid event is parsed and stored as usual, so the
    # byte policy never rejects a request that fits.
    with _make_app_client(monkeypatch, max_bytes=None) as client:
        response = client.post(
            "/events",
            content=json.dumps(_valid_event()).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 201
    get_settings.cache_clear()
