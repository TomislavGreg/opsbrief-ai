"""Tests for read-only mode and its middleware."""

import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from opsbrief.api.readonly import ReadOnlyMiddleware
from opsbrief.config import Settings, get_settings
from opsbrief.main import create_app


def _valid_event() -> dict[str, object]:
    return {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is one short",
        "occurred_at": "2026-07-29T09:30:00Z",
    }


def _read_only_client(monkeypatch: pytest.MonkeyPatch, **env: str) -> Iterator[TestClient]:
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        get_settings.cache_clear()


@pytest.fixture
def read_only_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from _read_only_client(monkeypatch, OPSBRIEF_READ_ONLY="true")


# --- Settings -------------------------------------------------------------


def test_read_only_is_off_by_default() -> None:
    assert Settings().read_only is False
    assert Settings().is_read_only() is False


def test_read_only_can_be_enabled() -> None:
    assert Settings(read_only="true").is_read_only() is True


def test_demo_data_implies_read_only() -> None:
    # A public demo seeds its own data and should take no writes over HTTP, so it is
    # read-only by default without a separate flag.
    assert Settings(demo_data="true").is_read_only() is True


# --- Middleware in isolation ----------------------------------------------


def _run(read_only: bool, method: str) -> int:
    """Drive the middleware at the ASGI level and return the response status.

    The inner app records that it ran, so a passed-through request can be told from
    a refused one even for a safe method.
    """
    ran = False

    async def inner(scope, receive, send):  # type: ignore[no-untyped-def]
        nonlocal ran
        ran = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    statuses: list[int] = []

    async def send(message: dict[str, object]) -> None:
        if message["type"] == "http.response.start":
            statuses.append(int(message["status"]))

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = ReadOnlyMiddleware(inner, read_only=read_only)
    scope = {"type": "http", "method": method, "headers": []}
    asyncio.run(middleware(scope, receive, send))
    # A refused write never reaches the inner app.
    assert ran is (statuses[0] == 200)
    return statuses[0]


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_read_only_refuses_unsafe_methods(method: str) -> None:
    assert _run(read_only=True, method=method) == 403


@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_read_only_allows_safe_methods(method: str) -> None:
    assert _run(read_only=True, method=method) == 200


@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
def test_disabled_middleware_is_transparent(method: str) -> None:
    assert _run(read_only=False, method=method) == 200


def test_non_http_scopes_pass_through() -> None:
    seen: list[str] = []

    async def inner(scope, receive, send):  # type: ignore[no-untyped-def]
        seen.append(scope["type"])

    middleware = ReadOnlyMiddleware(inner, read_only=True)
    asyncio.run(middleware({"type": "lifespan"}, None, None))  # type: ignore[arg-type]

    assert seen == ["lifespan"]


# --- Wired into the application -------------------------------------------


def test_reads_still_work_in_read_only_mode(read_only_client: TestClient) -> None:
    assert read_only_client.get("/health").status_code == 200
    assert read_only_client.get("/events").status_code == 200
    assert read_only_client.get("/risks").status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/events", _valid_event()),
        ("post", "/events/batch", {"events": [_valid_event()]}),
        (
            "post",
            "/incidents",
            {"title": "Ticketing down", "severity": "high", "event_ids": ["e1"]},
        ),
        ("post", "/incidents/whatever/resolution", {"note": "done"}),
        ("post", "/incidents/whatever/transition", {"status": "investigating"}),
        ("post", "/incidents/whatever/events", {"event_ids": ["e2"]}),
        ("delete", "/incidents/whatever/events/e1", None),
        ("post", "/webhooks/events", {"events": [_valid_event()]}),
    ],
)
def test_write_routes_are_refused_in_read_only_mode(
    read_only_client: TestClient, method: str, path: str, payload: dict[str, object] | None
) -> None:
    # Every mutation route is closed uniformly, ahead of routing, signature checks or
    # body parsing, so the refusal does not depend on the route existing for the id.
    response = read_only_client.request(method.upper(), path, json=payload)

    assert response.status_code == 403
    assert "read-only" in response.json()["detail"]
    # Nothing was stored: the store is still empty.
    assert read_only_client.get("/events").json()["total"] == 0


def test_read_only_write_refusal_leaves_the_store_untouched(read_only_client: TestClient) -> None:
    read_only_client.post("/events", json=_valid_event())

    assert read_only_client.get("/events").json()["total"] == 0


def test_writes_succeed_when_read_only_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    # The default deployment still accepts writes, so the switch is off unless set.
    for client in _read_only_client(monkeypatch):
        assert client.post("/events", json=_valid_event()).status_code == 201


def test_demo_mode_serves_reads_but_refuses_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Demo-data mode seeds events at startup (a read returns them) yet refuses an
    # HTTP write, so a public demo is populated and safe at once.
    for client in _read_only_client(monkeypatch, OPSBRIEF_DEMO_DATA="true"):
        assert client.get("/events").json()["total"] > 0
        assert client.post("/events", json=_valid_event()).status_code == 403
