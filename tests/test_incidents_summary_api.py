"""Tests for the incident-summary endpoint."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from opsbrief.ai import AIProviderError, CompletionRequest, CompletionResponse
from opsbrief.api.dependencies import get_ai_provider, get_excluded_ai_context_fields


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
    response = client.get("/incidents/missing/summary")

    assert response.status_code == 404
    assert "missing" in response.json()["detail"]


def test_summary_carries_the_incident_and_traces_to_its_events(client: TestClient) -> None:
    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id])

    response = client.get(f"/incidents/{incident_id}/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["incident_id"] == incident_id
    assert body["status"] == "open"
    assert body["severity"] == "high"
    assert body["source_event_ids"] == [event_id]
    assert body["missing_event_ids"] == []
    assert isinstance(body["summary"], str)
    assert body["model"]
    assert body["output_version"]


def test_a_cited_event_with_no_stored_record_is_reported_missing(client: TestClient) -> None:
    # An incident may cite an event the store never held; the summary names the gap
    # rather than failing the request.
    incident_id = declare_incident(client, ["gone"])

    body = client.get(f"/incidents/{incident_id}/summary").json()

    assert body["missing_event_ids"] == ["gone"]
    assert body["confidence"] == "none"


def test_summary_is_a_bounded_single_line(client: TestClient) -> None:
    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id])

    summary = client.get(f"/incidents/{incident_id}/summary").json()["summary"]

    assert "\n" not in summary
    assert len(summary) <= 1_000


def test_configured_excluded_fields_are_held_back_from_the_model(client: TestClient) -> None:
    class RecordingProvider:
        name = "recording"

        def __init__(self) -> None:
            self.requests: list[CompletionRequest] = []

        def complete(self, request: CompletionRequest) -> CompletionResponse:
            self.requests.append(request)
            return CompletionResponse(text="A summary.", model=self.name)

    event_id = post_event(client, subject="Steward Jane Doe did not report")
    incident_id = declare_incident(client, [event_id])
    provider = RecordingProvider()
    client.app.dependency_overrides[get_ai_provider] = lambda: provider
    client.app.dependency_overrides[get_excluded_ai_context_fields] = lambda: frozenset({"subject"})
    try:
        response = client.get(f"/incidents/{incident_id}/summary")
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)
        client.app.dependency_overrides.pop(get_excluded_ai_context_fields, None)

    assert response.status_code == 200
    material = provider.requests[0].input
    assert "Steward Jane Doe did not report" not in material
    assert "[excluded]" in material


def test_a_provider_outage_still_returns_the_deterministic_summary(client: TestClient) -> None:
    class FailingProvider:
        name = "failing"

        def complete(self, request: CompletionRequest) -> CompletionResponse:
            raise AIProviderError("transport failed")

    event_id = post_event(client)
    incident_id = declare_incident(client, [event_id])
    client.app.dependency_overrides[get_ai_provider] = FailingProvider
    try:
        response = client.get(f"/incidents/{incident_id}/summary")
    finally:
        client.app.dependency_overrides.pop(get_ai_provider, None)

    assert response.status_code == 200
    body = response.json()
    assert body["summary"] == ""
    assert body["source_event_ids"] == [event_id]
    assert any("unavailable" in note.lower() for note in body["notes"])
