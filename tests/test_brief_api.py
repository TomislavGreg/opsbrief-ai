"""Tests for the daily-brief endpoint."""

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


def test_no_events_gives_a_brief_that_reports_the_gap(client: TestClient) -> None:
    response = client.get("/brief")

    assert response.status_code == 200
    body = response.json()
    assert body["risks"] == []
    assert body["source_event_ids"] == []
    assert body["model"]
    assert body["generated_at"]
    assert isinstance(body["summary"], str)
    assert any("no source data" in note.lower() for note in body["notes"])


def test_brief_carries_the_risks_and_traces_to_their_events(client: TestClient) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    overdue_id = post_event(client, due_at=(now - timedelta(hours=2)).isoformat())

    body = client.get("/brief").json()

    assert [risk["rule"] for risk in body["risks"]] == ["overdue_work"]
    assert body["risks"][0]["event_ids"] == [overdue_id]
    assert overdue_id in body["source_event_ids"]


def test_brief_summary_is_a_bounded_single_line(client: TestClient) -> None:
    # The default build phrases with the fake provider; whatever it returns, the
    # summary is constrained to a bounded single line as untrusted output.
    post_event(client)

    summary = client.get("/brief").json()["summary"]

    assert "\n" not in summary
    assert len(summary) <= 1_000


def test_endpoint_takes_no_parameters(client: TestClient) -> None:
    # A stray query parameter does not break the endpoint; it reports the whole
    # current picture regardless.
    assert client.get("/brief", params={"source": "tasks"}).status_code == 200
