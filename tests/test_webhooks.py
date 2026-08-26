"""Tests for webhook signature verification."""

import pytest

from opsbrief.webhooks import (
    SIGNATURE_HEADER,
    SIGNATURE_PREFIX,
    TIMESTAMP_HEADER,
    WebhookAuthError,
    compute_signature,
    verify_webhook_signature,
)

SECRET = "a-sufficiently-long-shared-secret"
BODY = b'{"events": [{"source": "rostering", "event_type": "shift.unfilled"}]}'
NOW = 1_757_650_800


def signed(
    *,
    secret: str = SECRET,
    body: bytes = BODY,
    timestamp: int = NOW,
) -> dict[str, str]:
    """Return the two signature headers for a delivery signed at ``timestamp``."""
    stamp = str(timestamp)
    return {
        TIMESTAMP_HEADER: stamp,
        SIGNATURE_HEADER: compute_signature(secret, stamp, body),
    }


def verify(headers: dict[str, str], *, body: bytes = BODY, now: int = NOW) -> None:
    """Run verification against a header mapping, as the router will."""
    verify_webhook_signature(
        secret=SECRET,
        body=body,
        timestamp_header=headers.get(TIMESTAMP_HEADER),
        signature_header=headers.get(SIGNATURE_HEADER),
        now=now,
    )


def test_a_correctly_signed_delivery_verifies() -> None:
    verify(signed())  # does not raise


def test_signature_carries_the_algorithm_prefix() -> None:
    assert compute_signature(SECRET, str(NOW), BODY).startswith(SIGNATURE_PREFIX)


def test_the_signature_covers_the_timestamp() -> None:
    # Same body and secret, different signed timestamp: signatures must differ,
    # so a captured request cannot be re-timestamped.
    assert compute_signature(SECRET, str(NOW), BODY) != compute_signature(
        SECRET, str(NOW + 1), BODY
    )


def test_an_unset_secret_is_refused() -> None:
    with pytest.raises(WebhookAuthError, match="secret is not configured"):
        verify_webhook_signature(
            secret="",
            body=BODY,
            timestamp_header=str(NOW),
            signature_header=compute_signature(SECRET, str(NOW), BODY),
            now=NOW,
        )


def test_a_missing_timestamp_header_is_refused() -> None:
    headers = signed()
    del headers[TIMESTAMP_HEADER]
    with pytest.raises(WebhookAuthError, match=TIMESTAMP_HEADER):
        verify(headers)


def test_a_missing_signature_header_is_refused() -> None:
    headers = signed()
    del headers[SIGNATURE_HEADER]
    with pytest.raises(WebhookAuthError, match=SIGNATURE_HEADER):
        verify(headers)


def test_a_non_integer_timestamp_is_refused() -> None:
    headers = signed()
    headers[TIMESTAMP_HEADER] = "not-a-number"
    with pytest.raises(WebhookAuthError, match="not an integer"):
        verify(headers)


def test_a_timestamp_too_far_in_the_past_is_refused() -> None:
    with pytest.raises(WebhookAuthError, match="skew window"):
        verify(signed(timestamp=NOW - 3600))


def test_a_timestamp_too_far_in_the_future_is_refused() -> None:
    with pytest.raises(WebhookAuthError, match="skew window"):
        verify(signed(timestamp=NOW + 3600))


def test_a_timestamp_at_the_edge_of_the_window_verifies() -> None:
    verify(signed(timestamp=NOW - 300))  # exactly at the default tolerance
    verify(signed(timestamp=NOW + 300))


def test_the_skew_window_is_checked_before_the_signature() -> None:
    # A stale delivery is refused for the timestamp even when the signature is
    # nonsense, so an old capture is turned away up front.
    with pytest.raises(WebhookAuthError, match="skew window"):
        verify_webhook_signature(
            secret=SECRET,
            body=BODY,
            timestamp_header=str(NOW - 3600),
            signature_header="sha256=deadbeef",
            now=NOW,
        )


def test_a_signature_without_the_prefix_is_refused() -> None:
    headers = signed()
    headers[SIGNATURE_HEADER] = compute_signature(SECRET, str(NOW), BODY).removeprefix(
        SIGNATURE_PREFIX
    )
    with pytest.raises(WebhookAuthError, match="prefixed"):
        verify(headers)


def test_a_tampered_body_is_refused() -> None:
    with pytest.raises(WebhookAuthError, match="does not match"):
        verify(signed(), body=BODY + b" ")


def test_a_signature_made_with_another_secret_is_refused() -> None:
    headers = signed(secret="a-different-long-enough-secret")
    with pytest.raises(WebhookAuthError, match="does not match"):
        verify(headers)


def test_a_custom_tolerance_widens_the_window() -> None:
    verify_webhook_signature(
        secret=SECRET,
        body=BODY,
        timestamp_header=str(NOW - 3600),
        signature_header=compute_signature(SECRET, str(NOW - 3600), BODY),
        now=NOW,
        tolerance_seconds=7200,
    )
