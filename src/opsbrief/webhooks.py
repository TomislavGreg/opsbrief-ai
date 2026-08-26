"""Authenticating webhook deliveries with an HMAC signature.

The webhook front door reuses the existing event contract, so the one new piece
of machinery it needs is a way to prove that a delivery was signed by a holder of
the shared secret and was neither altered nor replayed. This module is that piece.

Verification is deterministic and runs over the raw request bytes, because the
signature is computed over those bytes: re-serialising parsed JSON could change
them and break the comparison. It fails closed: a missing header, a malformed
value, a stale timestamp or a signature mismatch is a refusal, never an accepted
write. Nothing here logs or echoes the secret or the computed signature.
"""

import hashlib
import hmac

#: Header carrying the Unix-seconds timestamp the sender signed against.
TIMESTAMP_HEADER = "X-OpsBrief-Timestamp"

#: Header carrying the signature, prefixed with the algorithm it was computed with.
SIGNATURE_HEADER = "X-OpsBrief-Signature"

#: Algorithm prefix on the signature value. An explicit prefix leaves room for a
#: future scheme to be added without breaking existing senders.
SIGNATURE_PREFIX = "sha256="

#: Default clock skew, in seconds, a signed timestamp may fall outside (past or
#: future) before the delivery is refused as a possible replay.
DEFAULT_TIMESTAMP_TOLERANCE_SECONDS = 300

#: Shortest shared secret accepted, so a trivially guessable secret fails loudly
#: at startup rather than silently weakening the path.
MIN_SECRET_LENGTH = 16


class WebhookAuthError(Exception):
    """A webhook delivery failed authentication.

    The ``reason`` is a short, non-sensitive description safe to return to the
    caller: it names why the delivery was refused but never the secret or the
    computed signature.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    """Return the signature header value for ``body`` signed at ``timestamp``.

    The signed material is ``"<timestamp>." + body``, so the timestamp is part of
    what is signed and cannot be changed without invalidating the signature. That
    is what makes the skew window meaningful against replay: a captured request
    cannot be re-timestamped. The sender computes this same value.
    """
    signed = timestamp.encode("utf-8") + b"." + body
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{digest}"


def verify_webhook_signature(
    *,
    secret: str,
    body: bytes,
    timestamp_header: str | None,
    signature_header: str | None,
    now: int,
    tolerance_seconds: int = DEFAULT_TIMESTAMP_TOLERANCE_SECONDS,
) -> None:
    """Verify a signed webhook delivery, raising :class:`WebhookAuthError` on failure.

    The checks run in the order the design fixes, cheapest and most decisive
    first:

    1. A configured secret and both headers must be present.
    2. The timestamp must be an integer and fall inside the skew window, judged
       against ``now``, before any further work, so an old capture is refused up
       front.
    3. The signature must carry the ``sha256=`` prefix, and the HMAC recomputed
       over ``"<timestamp>." + body`` with ``secret`` must match it in constant
       time, so a mismatch leaks no timing signal.

    Returns ``None`` when the delivery is authentic; the caller then parses and
    validates the body through the existing event contract. The timestamp used to
    recompute the signature is the exact header value the sender signed against,
    not a reformatted one.
    """
    if not secret:
        raise WebhookAuthError("webhook secret is not configured")
    if timestamp_header is None:
        raise WebhookAuthError(f"missing {TIMESTAMP_HEADER} header")
    if signature_header is None:
        raise WebhookAuthError(f"missing {SIGNATURE_HEADER} header")

    try:
        timestamp = int(timestamp_header)
    except ValueError:
        raise WebhookAuthError(f"{TIMESTAMP_HEADER} is not an integer") from None

    if abs(now - timestamp) > tolerance_seconds:
        raise WebhookAuthError("timestamp is outside the allowed skew window")

    if not signature_header.startswith(SIGNATURE_PREFIX):
        raise WebhookAuthError(f"signature is not prefixed with {SIGNATURE_PREFIX!r}")

    expected = compute_signature(secret, timestamp_header, body)
    if not hmac.compare_digest(expected, signature_header):
        raise WebhookAuthError("signature does not match")
