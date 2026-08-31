# Game Center Integration Contract

Status: documentation of the contract as implemented. This document describes how
a separate operations platform (Game Center) integrates with OpsBrief AI: what it
sends, how it sends it, what OpsBrief AI does with it, and what it reads back. It
ties together pieces documented elsewhere (the event contract, the authenticated
webhook, the risk rules, the read endpoints) into one account a platform team can
build against.

It records the contract that exists today. It is not a roadmap: features not yet
implemented are called out as out of scope at the end.

## Shape of the integration

The integration is deliberately one-directional and narrow.

```
Game Center platform                      OpsBrief AI
--------------------                      -----------
operational events  --- POST (signed) -->  ingestion, storage
                                           deterministic risk rules
                                           briefs and incident summaries
briefs, risks,      <-- GET (read) ------  read API
incidents
```

The platform pushes operational events to an authenticated webhook. OpsBrief AI
stores them, applies its deterministic risk rules, and generates briefs and
incident summaries. The platform reads those back over the existing read API.
There is no shared database, no callback into the platform, and no coupling to any
platform-specific schema: sports-operations specifics travel as `event_type` and
`metadata`, never as bespoke fields or code paths.

Because the flow is one-directional, the platform owns the integration's timing.
OpsBrief AI does not call out. The platform posts events as they occur and polls
the read endpoints when it wants the current picture.

## Write path

Events enter through one endpoint:

```
POST /webhooks/events
```

The body is the batch shape `POST /events/batch` accepts, an `events` array of
event objects (a single event is a batch of one, between 1 and 500 per request).
Each delivery is authenticated with an HMAC-SHA256 signature over the raw request
body, keyed by a shared secret. The full scheme (the two headers, the signed
timestamp and skew window, the constant-time comparison, and the disabled-without-
a-secret behaviour) is described in
[`webhook-ingestion.md`](webhook-ingestion.md) and summarised in the README's
Webhook Ingestion section.

The response is `202 Accepted` with a `count` of newly stored events and the
stored events in submitted order. A signature failure is `401`, an oversized body
`413`, and a body that fails the event contract `422` with nothing stored.

### Idempotency

Networks retry, so the same delivery can arrive more than once. Every event should
carry an `external_id`, the producer's own identifier for it. OpsBrief AI
deduplicates on `(source, external_id)`: an event whose key it has already stored
returns the previously stored event rather than a duplicate, and `count` reports
only what was newly stored. A retried delivery, whether the whole batch or a single
event, is therefore safe. The first submission wins: resending the same
`external_id` with changed fields returns the event as first stored, so OpsBrief AI
is a system of record for what it first accepted, not a mutable mirror of the
platform.

## Event modelling conventions

The event contract is generic (the full field reference is in the README's Event
Schema section). What follows is how the platform is expected to populate it, so
that the deterministic risk rules recognise the operational situations they are
meant to.

| Field | Convention |
|-------|------------|
| `source` | The producing subsystem, for example `rostering`, `tasks`, `integrations`, `quality`, `facilities`. |
| `event_type` | A lowercase dotted name, for example `shift.unfilled`, `task.overdue`, `integration.failed`. Domain specifics live here, not in new fields. |
| `subject` | A one-line human-readable description, shown in briefs and timelines. |
| `occurred_at` | When it happened, with a timezone offset. Stored as UTC. |
| `severity` | The producer's own view (`info` to `critical`). Risk rules may disagree; they never defer to it blindly. |
| `status` | The state of the work or system: `open`, `in_progress`, `blocked`, `overdue`, `failed`, `resolved`, `cancelled`. The rules read this directly. |
| `entity_type`, `entity_id` | What the event is about, supplied together. An integration or task keeps a stable `entity_id` across its events so recurrence and recovery can be attributed to it. |
| `due_at` | The deadline, when the work has one. The overdue rule reads it. |
| `external_id` | The producer's identifier for the event, for idempotency (above). |
| `metadata` | Flat scalar detail specific to the producing system, at most 25 entries. Keep sensitive values here, where redaction can mask them. |

The rules are deterministic and rule-based, so what the platform sends decides what
is recognised:

- **Overdue work** is raised for an event carrying a `due_at` in the past whose
  `status` is not `resolved` or `cancelled`.
- **Blocked work** is raised for an event whose `status` is `blocked`.
- **Repeated integration failure** is raised once an `entity_id` has produced three
  or more `failed` events within a week without a later `resolved` event for the
  same `entity_id`. A recovery clears it, so send the `resolved` event when the
  integration comes back.

Sending a later `resolved` (or `shift.filled`, `task.completed`) event for the same
`entity_id` is how the platform tells OpsBrief AI a situation has cleared. The risk
picture is recomputed from the current events every time it is read, so a cleared
situation stops being reported.

Sensitive and personal data must not be sent. This is a public project (see
[`../SECURITY.md`](../SECURITY.md)); keep anything sensitive in `metadata`, where a
value whose key names a sensitive term is redacted before storage, and prefer
opaque identifiers over names in the fields the service reasons over.

## Read path

The platform reads the current picture over the existing read endpoints. All are
read-only and take no authentication (the design adds authentication to the write
path only):

| Endpoint | Returns |
|----------|---------|
| `GET /events` | Stored events, newest first, filtered by source, type, severity or status and paginated. |
| `GET /events/{event_id}` | One stored event, or 404. |
| `GET /risks` | The current risks across all stored events, most urgent first, each naming the rule and source events behind it. |
| `GET /brief` | The current daily operations brief: a model-phrased summary alongside the deterministic risks, notes and source event IDs. |
| `GET /incidents`, `GET /incidents/{incident_id}` | Tracked incidents, listed or by id. |
| `GET /incidents/{incident_id}/summary` | One incident summarised: a model-phrased summary alongside the deterministic status, severity, span and source event IDs. |

Incidents are the one place the platform may also write, through
`POST /incidents` and `POST /incidents/{incident_id}/resolution`, when it wants
OpsBrief AI to track a disruption as a stateful record. This is optional: the read
path alone gives the platform briefs and risks without declaring anything.

Every generated statement traces back to the source event IDs behind it, so the
platform can always resolve a brief or a risk to the events it sent.

## Stability and versioning

- **The event contract is generic and additive.** New operational situations arrive
  as new `event_type` and `metadata` values, not as schema changes, so the platform
  can model new things without a coordinated release. Unknown top-level fields are
  rejected, so a mistyped payload fails loudly rather than being silently dropped.
- **Generated output is versioned.** A daily brief and an incident summary each
  carry an `output_version` (the structure) and a `prompt_version` (the wording),
  so the platform can detect a change in either rather than being surprised by one.
- **Structural changes are visible, not silent.** When the shape of generated output
  changes, its `output_version` changes with it.

## Security boundary

- Authentication covers the one machine-to-machine write path only. The read
  endpoints are unauthenticated by design; a deployment that needs to restrict them
  places OpsBrief AI behind its own network boundary.
- Model output is treated as untrusted data: only the prose summary of a brief or
  incident comes from a model, and it is constrained before use. Everything the
  platform acts on (risks, source event IDs, incident state) is deterministic.
- No secrets or private data live in OpsBrief AI or this repository. The shared
  webhook secret is supplied through the environment.

## Out of scope

Deliberately not part of the contract today, to keep it small until there is a
concrete need:

- Any push from OpsBrief AI back to the platform (webhooks out, callbacks,
  streaming). The platform polls.
- Read-side authentication, per-tenant isolation and rate limiting.
- Per-producer webhook secrets, secret rotation and multiple active secrets (see
  [`webhook-ingestion.md`](webhook-ingestion.md)).
- Any platform-specific event type or field baked into OpsBrief AI. Sports-operations
  specifics stay in `event_type` and `metadata`.
