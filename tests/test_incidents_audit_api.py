"""Tests for the incident-summary audit endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from opsbrief.ai import AIProviderError, CompletionRequest, CompletionResponse
from opsbrief.api.dependencies import get_ai_provider


def submission(**overrides: Any) -> dict[str, Any]:
    """Return a valid event submission payload, with ``overrides`` applied."""
    now = datetime.now(UTC).replace(microsecond=0)
    payload: dict[str, Any] = {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": "Ticketing webhook failed",
        "occurred_at": (now - timedelta(hours=2)).isoformat(),
        "severity": "high",
        "status": "failed",
    }
    payload.update(overrides)
    return payload


def post_event(client: TestClient, **overrides: Any) -> str:
    """Submit an event and return the identifier it was stored under."""
    response = client.post("/events", json=submission(**overrides))
    assert response.status_code == 201
    return response.json()["id"]


def declare_incident(client: TestClient, event_ids: list[str], **overrides: Any) -> str:
    """Declare an incident over ``event_ids`` and return its identifier."""
    payload: dict[str, Any] = {
        "title": "Ticketing integration failing repeatedly",
        "severity": "high",
        "event_ids": event_ids,
    }
    payload.update(overrides)
    response = client.post("/incidents", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def test_an_unknown_incident_is_a_404(client: TestClient) -> None:
    response = client.get("/incidents/missing/audit")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_audit_names_the_incident_and_traces_to_its_events(client: TestClient) -> None:
    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id])

    response = client.get(f"/incidents/{incident_id}/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "incident_summary"
    assert body["subject_id"] == incident_id
    assert body["source_event_ids"] == [event_id]
    assert body["source_event_count"] == 1
    assert body["missing_event_ids"] == []
    assert body["model"]
    assert body["prompt_version"]
    assert body["output_version"]


def test_audit_agrees_with_the_summary_it_describes(client: TestClient) -> None:
    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id])

    summary = client.get(f"/incidents/{incident_id}/summary").json()
    audit = client.get(f"/incidents/{incident_id}/audit").json()

    assert audit["subject_id"] == summary["incident_id"]
    assert audit["source_event_ids"] == summary["source_event_ids"]
    assert audit["missing_event_ids"] == summary["missing_event_ids"]
    assert audit["model"] == summary["model"]
    assert audit["prompt_version"] == summary["prompt_version"]
    assert audit["output_version"] == summary["output_version"]
    assert audit["confidence"] == summary["confidence"]
    assert audit["warning_codes"] == [warning["code"] for warning in summary["warnings"]]


def test_a_provider_outage_still_returns_the_audit(client: TestClient) -> None:
    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id])

    class FailingProvider:
        name = "unreachable"

        def complete(self, request: CompletionRequest) -> CompletionResponse:
            raise AIProviderError("transport failed")

    client.app.dependency_overrides[get_ai_provider] = FailingProvider
    try:
        response = client.get(f"/incidents/{incident_id}/audit")
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "unreachable"
    assert "model_unavailable" in body["warning_codes"]
