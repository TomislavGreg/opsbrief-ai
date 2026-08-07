"""Tests for the risk-list endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient


def submission(**overrides: Any) -> dict[str, Any]:
    """Return a valid event submission payload, with ``overrides`` applied."""
    now = datetime.now(UTC).replace(microsecond=0)
    payload: dict[str, Any] = {
        "source": "tasks",
        "event_type": "task.update",
        "subject": "A work item",
        "occurred_at": (now - timedelta(hours=6)).isoformat(),
    }
    payload.update(overrides)
    return payload


def post_event(client: TestClient, **overrides: Any) -> str:
    """Submit an event and return the identifier it was stored under."""
    response = client.post("/events", json=submission(**overrides))
    assert response.status_code == 201
    return response.json()["id"]


def test_no_events_gives_an_empty_snapshot(client: TestClient) -> None:
    response = client.get("/risks")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["risks"] == []
    assert body["generated_at"]


def test_overdue_event_surfaces_as_a_traceable_risk(client: TestClient) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    event_id = post_event(client, due_at=(now - timedelta(hours=1)).isoformat())

    body = client.get("/risks").json()

    assert body["total"] == 1
    risk = body["risks"][0]
    assert risk["rule"] == "overdue_work"
    assert risk["event_ids"] == [event_id]
    assert risk["severity"] in {"medium", "high"}


def test_risks_are_returned_most_urgent_first(client: TestClient) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    # Blocked for two days, so high; overdue only within the hour, so medium.
    blocked_id = post_event(
        client,
        subject="Blocked task",
        status="blocked",
        occurred_at=(now - timedelta(days=2)).isoformat(),
    )
    post_event(client, subject="Just-late task", due_at=(now - timedelta(minutes=30)).isoformat())

    body = client.get("/risks").json()

    assert body["total"] == 2
    assert [risk["severity"] for risk in body["risks"]] == ["high", "medium"]
    assert body["risks"][0]["event_ids"] == [blocked_id]


def test_resolved_work_raises_no_risk(client: TestClient) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    post_event(client, status="resolved", due_at=(now - timedelta(days=1)).isoformat())

    body = client.get("/risks").json()

    assert body["total"] == 0


def test_unknown_query_parameter_is_ignored(client: TestClient) -> None:
    # The endpoint takes no parameters; a stray one does not break it.
    assert client.get("/risks", params={"source": "tasks"}).status_code == 200
