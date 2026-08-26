"""Authenticated webhook ingestion endpoint.

``POST /webhooks/events`` is a thin authenticated front door over the batch
ingestion the service already has. It reuses the existing event contract, so a
delivery is validated, redacted and deduplicated by exactly the same code path a
direct ``POST /events/batch`` submission is. The only work unique to the webhook
is authenticating the caller: the body is size-bounded, the HMAC signature is
verified over the raw bytes, and only then is the body parsed and stored.
"""

import json
import time

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import ValidationError

from opsbrief.api.dependencies import EventStoreDependency, SensitiveMetadataKeysDependency
from opsbrief.config import get_settings
from opsbrief.events import EventBatch, EventBatchResult
from opsbrief.services import record_events
from opsbrief.webhooks import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    WebhookAuthError,
    verify_webhook_signature,
)

#: Largest webhook body accepted, checked before the body is verified or parsed so
#: an oversized payload is refused with 413 rather than exhausting memory. A full
#: 500-event batch of maximal events fits comfortably under this bound.
MAX_WEBHOOK_BODY_BYTES = 8 * 1024 * 1024

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _reject_if_too_large(declared_length: str | None, actual_length: int) -> None:
    """Refuse a body that exceeds the size bound, by declared or actual length."""
    if declared_length is not None:
        try:
            if int(declared_length) > MAX_WEBHOOK_BODY_BYTES:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="webhook body exceeds the maximum size",
                )
        except ValueError:
            pass  # A malformed Content-Length is caught by the actual-length check.
    if actual_length > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="webhook body exceeds the maximum size",
        )


@router.post(
    "/events",
    response_model=EventBatchResult,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest a signed batch of operational events",
    response_description="The stored events, with their service-assigned identifiers.",
    responses={
        401: {"description": "The signature was missing, malformed, expired or mismatched."},
        413: {"description": "The body exceeds the configured size bound."},
        422: {"description": "The body failed the event contract; nothing was stored."},
    },
)
async def ingest_events(
    request: Request,
    store: EventStoreDependency,
    sensitive_keys: SensitiveMetadataKeysDependency,
) -> EventBatchResult:
    """Authenticate a signed delivery and store its events.

    The webhook is disabled unless a secret is configured, so an unconfigured
    deployment answers 404 and never takes an unauthenticated write. A configured
    deployment size-bounds the body (413), verifies the HMAC signature over the
    raw bytes (401 on any failure), then validates the body through the existing
    batch contract (422 on failure) and stores it, answering 202 with the same
    result a direct batch submission returns. Retried deliveries are recognised by
    the existing ``(source, external_id)`` deduplication, so ``count`` reports only
    what was newly stored.
    """
    settings = get_settings()
    if not settings.webhook_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="the webhook is not configured")

    body = await request.body()
    _reject_if_too_large(request.headers.get("content-length"), len(body))

    try:
        verify_webhook_signature(
            secret=settings.webhook_secret,
            body=body,
            timestamp_header=request.headers.get(TIMESTAMP_HEADER),
            signature_header=request.headers.get(SIGNATURE_HEADER),
            now=int(time.time()),
            tolerance_seconds=settings.webhook_timestamp_tolerance_seconds,
        )
    except WebhookAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=exc.reason) from exc

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="webhook body is not valid JSON",
        ) from exc

    try:
        batch = EventBatch.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=json.loads(exc.json()),
        ) from exc

    return record_events(store, batch, sensitive_keys=sensitive_keys)
