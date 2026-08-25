# Authenticated Webhook Ingestion Design

Status: design, not yet implemented. This document records the intended design so
the implementation (tracked as AI-061) has a clear contract to build against. It
describes what the webhook accepts, how a request is authenticated, and how the
service protects itself. It does not add authentication to the running code:
until AI-061 lands, the only way in is the existing `POST /events` and
`POST /events/batch` endpoints.

## Why a webhook

OpsBrief AI is built so a separate operations platform (Game Center) can use it
as its AI operations module. The integration is deliberately one-directional and
narrow: the platform posts operational events, OpsBrief AI stores them, applies
its deterministic risk rules and generates briefs and incident summaries, and the
platform reads those back over the existing read API. There is no shared database
and no coupling to any platform-specific schema.

The platform runs on a different host from OpsBrief AI, so ingestion needs to
authenticate the caller and protect the payload in transit. A webhook with a
signed body is the standard shape for that: the sender proves it holds a shared
secret and that the body was not altered, without OpsBrief AI having to manage
user accounts or sessions. Authentication is scoped to this one machine-to-machine
path; the product still has no end-user authentication, in line with the project's
direction of not adding auth before the core product works.

## Endpoint

```
POST /webhooks/events
Content-Type: application/json
```

The webhook is a thin authenticated front door over the ingestion the service
already has. It reuses the existing event contract rather than defining a new one:
the request body is exactly the batch body `POST /events/batch` accepts, an
`events` array of `EventInput` objects. Reusing the contract means a webhook
delivery is validated, redacted and deduplicated by the same code path a direct
submission is, and sports-operations specifics keep arriving as `event_type` and
`metadata` rather than as bespoke fields.

A single-event delivery is a batch of one, so one endpoint covers both and there
is no second shape to authenticate and validate. The batch bound the service
already enforces (1 to 500 events) applies unchanged.

### Response

On success the endpoint answers `202 Accepted` with the same body
`POST /events/batch` returns: a `count` of newly stored events and the stored
events in submitted order. `202` rather than `201` reflects that the caller is a
delivery mechanism handing work off, not a user creating a named resource, but the
stored result is returned in full so the platform can reconcile immediately.

Failures are reported by status so a caller can tell them apart:

| Status | Meaning |
|--------|---------|
| `202 Accepted` | Delivery authenticated and stored. |
| `401 Unauthorized` | Missing, malformed, expired or mismatched signature. |
| `413 Payload Too Large` | Body exceeds the configured size bound. |
| `422 Unprocessable Entity` | Body failed the event contract; nothing stored. |

The body of an error names the field or reason at fault, as the existing
endpoints already do, and never echoes the secret or the computed signature.

## Authentication

The webhook is authenticated with an HMAC signature over the raw request body,
keyed by a shared secret. This is the same scheme GitHub and Stripe use for their
webhooks, chosen here because it is simple, standard, verifiable offline, and
authenticates the payload's integrity as well as the sender: a tampered body
produces a different signature. It needs no key distribution beyond the one shared
secret and no session state on the server.

The sender computes the signature over the exact bytes of the request body and
sends it, with the timestamp it signed against, in two headers:

```
X-OpsBrief-Timestamp: 1757650800
X-OpsBrief-Signature: sha256=<hex HMAC-SHA256 of "<timestamp>." + raw body>
```

The timestamp is a Unix time in seconds. It is part of the signed material (the
signature covers `"<timestamp>." + raw_body`), so it cannot be changed without
invalidating the signature. Signing the timestamp alongside the body is what makes
replay protection meaningful: a captured request cannot be re-timestamped.

The server verifies a delivery by:

1. Reading the timestamp and signature headers; a request missing either is
   `401`.
2. Rejecting a timestamp outside the allowed skew window (default five minutes,
   past or future) before doing any further work, so an old capture is refused up
   front. This bounds replay to the window; combined with idempotency (below) a
   replay inside the window still does not double-store.
3. Recomputing the HMAC over `"<timestamp>." + raw_body` with the configured
   secret and comparing it to the supplied signature in constant time
   (`hmac.compare_digest`), so a mismatch is `401` and the comparison leaks no
   timing signal.
4. Only then parsing and validating the body through the existing event contract.

Verification runs on the raw request bytes, before JSON parsing, because the
signature is over those bytes: re-serializing parsed JSON could change them and
break the comparison.

### The secret

The shared secret is read from `OPSBRIEF_WEBHOOK_SECRET`, an environment variable,
and never lives in the repository, exactly as the data policy requires. When the
variable is unset the webhook route is disabled rather than defaulting to an empty
or well-known secret: an unconfigured deployment must not accept unauthenticated
writes. A short minimum length is enforced at startup so a trivially guessable
secret fails loudly rather than silently weakening the path.

One shared secret authenticates the platform as a whole. Per-producer keys, key
rotation and multiple active secrets are deliberately out of scope for the first
implementation; the header carries an explicit `sha256=` algorithm prefix so a
future scheme can be added without breaking existing senders.

## Idempotency

Networks retry. A platform that does not get a timely response will resend, so the
same delivery can arrive more than once. The webhook does not need new machinery
for this: the service already deduplicates on `(source, external_id)`, storing an
event once and returning the previously stored one on a resend. Producers set
`external_id` on each event, so a retried delivery, whether the whole batch or a
single event, is recognised and not stored twice, and `count` reports only what
was newly stored. Replay protection (the skew window) and idempotency (the dedup
key) are complementary: the window bounds how long a captured request is even
considered, and the dedup key makes a replay within the window a no-op.

## Protecting the service

- The body is size-bounded before it is read into memory or verified, so a large
  payload is refused with `413` rather than exhausting memory.
- Input stays untrusted. The signature proves who sent the body, not that the body
  is well-formed, so every event is still validated by the same Pydantic contract,
  redacted for sensitive metadata, and constrained exactly as a direct submission
  is.
- Nothing sensitive is logged. The secret, the computed signature and raw bodies
  are kept out of logs; a rejected delivery is logged by reason and status only.
- Verification is constant-time and fails closed: any missing header, parse
  failure, or unset secret results in refusal, never in accepting an
  unauthenticated write.

These choices extend the posture recorded in [`SECURITY.md`](../SECURITY.md)
rather than replacing it: deterministic rules still decide what matters, model
output is still untrusted, and now the one machine-to-machine write path is
authenticated and integrity-checked.

## Configuration summary

| Variable | Purpose | Default |
|----------|---------|---------|
| `OPSBRIEF_WEBHOOK_SECRET` | Shared secret for HMAC verification. Unset disables the webhook. | unset |
| `OPSBRIEF_WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` | Allowed clock skew for the signed timestamp. | `300` |

## Out of scope for this design

The following are intentionally deferred, to keep the first implementation small
and to avoid building machinery before there is a need for it:

- The implementation itself (the route, the verification service and its tests),
  tracked as AI-061.
- Per-producer secrets, secret rotation and multiple active secrets.
- Delivery receipts, retry queues or asynchronous processing: ingestion stays
  synchronous, and the platform retries on the existing idempotent path.
- Any read-side authentication: this design covers only the write path.
