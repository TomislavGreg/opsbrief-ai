"""Tests for the daily-brief audit endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from opsbrief.ai import AIProviderError, CompletionRequest, CompletionResponse
from opsbrief.api.dependencies import get_ai_provider


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


def test_no_events_gives_an_audit_that_reports_the_gap(client: TestClient) -> None:
    response = client.get("/brief/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "daily_brief"
    assert body["subject_id"] is None
    assert body["source_event_ids"] == []
    assert body["source_event_count"] == 0
    assert body["confidence"] == "none"
    assert "no_events" in body["warning_codes"]


def test_audit_traces_to_the_events_behind_the_brief(client: TestClient) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    overdue_id = post_event(client, due_at=(now - timedelta(hours=2)).isoformat())

    body = client.get("/brief/audit").json()

    assert body["kind"] == "daily_brief"
    assert body["model"]
    assert body["prompt_version"]
    assert body["output_version"]
    assert overdue_id in body["source_event_ids"]
    assert body["source_event_count"] == len(body["source_event_ids"])
    assert body["missing_event_ids"] == []


def test_audit_agrees_with_the_brief_it_describes(client: TestClient) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    post_event(client, due_at=(now - timedelta(hours=2)).isoformat())

    brief = client.get("/brief").json()
    audit = client.get("/brief/audit").json()

    assert audit["source_event_ids"] == brief["source_event_ids"]
    assert audit["model"] == brief["model"]
    assert audit["prompt_version"] == brief["prompt_version"]
    assert audit["output_version"] == brief["output_version"]
    assert audit["confidence"] == brief["confidence"]
    assert audit["warning_codes"] == [warning["code"] for warning in brief["warnings"]]


def test_a_provider_outage_still_returns_the_audit(client: TestClient) -> None:
    post_event(client)

    class FailingProvider:
        name = "unreachable"

        def complete(self, request: CompletionRequest) -> CompletionResponse:
            raise AIProviderError("transport failed")

    client.app.dependency_overrides[get_ai_provider] = FailingProvider
    try:
        response = client.get("/brief/audit")
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "unreachable"
    assert "model_unavailable" in body["warning_codes"]
