"""Tests for the authenticated webhook ingestion endpoint."""

import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from opsbrief.config import get_settings
from opsbrief.main import create_app
from opsbrief.webhooks import SIGNATURE_HEADER, TIMESTAMP_HEADER, compute_signature

SECRET = "a-sufficiently-long-shared-secret"


@pytest.fixture
def webhook_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Return a test client whose application has the webhook enabled."""
    monkeypatch.setenv("OPSBRIEF_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("OPSBRIEF_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        get_settings.cache_clear()


def event(**overrides: Any) -> dict[str, Any]:
    """Return a valid event payload, with ``overrides`` applied."""
    payload: dict[str, Any] = {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is one short",
        "occurred_at": "2026-07-29T09:30:00Z",
        "external_id": "roster-9931",
    }
    payload.update(overrides)
    return payload


def deliver(
    client: TestClient,
    events: list[dict[str, Any]],
    *,
    secret: str = SECRET,
    timestamp: int | None = None,
    body_override: bytes | None = None,
    sign_body: bytes | None = None,
) -> Any:
    """Post a signed webhook delivery and return the response.

    ``body_override`` sends different bytes than were signed (to model tampering);
    ``sign_body`` signs bytes other than those sent. By default the sent and
    signed bytes are the same serialisation of ``events``.
    """
    body = json.dumps({"events": events}).encode("utf-8")
    stamp = str(timestamp if timestamp is not None else int(time.time()))
    signature = compute_signature(secret, stamp, sign_body if sign_body is not None else body)
    return client.post(
        "/webhooks/events",
        content=body_override if body_override is not None else body,
        headers={
            "Content-Type": "application/json",
            TIMESTAMP_HEADER: stamp,
            SIGNATURE_HEADER: signature,
        },
    )


def test_a_signed_single_event_is_accepted(webhook_client: TestClient) -> None:
    response = deliver(webhook_client, [event()])

    assert response.status_code == 202
    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["id"]
    assert body["events"][0]["subject"] == "Steward shift for fixture 4821 is one short"


def test_a_signed_batch_is_accepted(webhook_client: TestClient) -> None:
    response = deliver(
        webhook_client,
        [
            event(external_id="roster-1"),
            event(
                external_id="integrations-1", source="integrations", event_type="integration.failed"
            ),
        ],
    )

    assert response.status_code == 202
    assert response.json()["count"] == 2


def test_a_stored_webhook_event_is_readable(webhook_client: TestClient) -> None:
    stored_id = deliver(webhook_client, [event()]).json()["events"][0]["id"]

    read = webhook_client.get(f"/events/{stored_id}")
    assert read.status_code == 200
    assert read.json()["id"] == stored_id


def test_a_resent_delivery_is_not_stored_twice(webhook_client: TestClient) -> None:
    first = deliver(webhook_client, [event()]).json()
    second = deliver(webhook_client, [event()]).json()

    assert first["count"] == 1
    assert second["count"] == 0  # recognised as a resubmission
    assert second["events"][0]["id"] == first["events"][0]["id"]


def test_a_missing_signature_is_unauthorized(webhook_client: TestClient) -> None:
    body = json.dumps({"events": [event()]}).encode("utf-8")
    response = webhook_client.post(
        "/webhooks/events",
        content=body,
        headers={TIMESTAMP_HEADER: str(int(time.time()))},
    )

    assert response.status_code == 401


def test_a_bad_signature_is_unauthorized(webhook_client: TestClient) -> None:
    response = deliver(webhook_client, [event()], secret="another-long-enough-secret")

    assert response.status_code == 401


def test_a_tampered_body_is_unauthorized(webhook_client: TestClient) -> None:
    # Sign the honest body but send an altered one.
    tampered = json.dumps({"events": [event(subject="Altered after signing")]}).encode("utf-8")
    response = deliver(webhook_client, [event()], body_override=tampered)

    assert response.status_code == 401


def test_an_expired_timestamp_is_unauthorized(webhook_client: TestClient) -> None:
    response = deliver(webhook_client, [event()], timestamp=int(time.time()) - 3600)

    assert response.status_code == 401


def test_an_invalid_json_body_is_rejected(webhook_client: TestClient) -> None:
    body = b"this is not json"
    stamp = str(int(time.time()))
    response = webhook_client.post(
        "/webhooks/events",
        content=body,
        headers={
            TIMESTAMP_HEADER: stamp,
            SIGNATURE_HEADER: compute_signature(SECRET, stamp, body),
        },
    )

    assert response.status_code == 422


def test_a_body_failing_the_event_contract_is_rejected(webhook_client: TestClient) -> None:
    response = deliver(webhook_client, [event(occurred_at="2026-07-29T09:30:00")])  # no offset

    assert response.status_code == 422
    # Nothing was stored.
    assert webhook_client.get("/events").json()["total"] == 0


def test_an_empty_batch_is_rejected(webhook_client: TestClient) -> None:
    response = deliver(webhook_client, [])

    assert response.status_code == 422


def test_an_oversized_body_is_rejected(
    webhook_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("opsbrief.api.webhooks.MAX_WEBHOOK_BODY_BYTES", 10)
    response = deliver(webhook_client, [event()])

    assert response.status_code == 413
    assert webhook_client.get("/events").json()["total"] == 0


def test_sensitive_metadata_is_redacted_over_the_webhook(webhook_client: TestClient) -> None:
    response = deliver(webhook_client, [event(metadata={"password": "hunter2", "required": 4})])

    stored = response.json()["events"][0]
    assert stored["metadata"]["password"] == "[redacted]"
    assert stored["metadata"]["required"] == 4


def test_the_webhook_is_disabled_without_a_secret(client: TestClient) -> None:
    # The shared ``client`` fixture configures no secret, so the route is disabled.
    response = deliver(client, [event()])

    assert response.status_code == 404
