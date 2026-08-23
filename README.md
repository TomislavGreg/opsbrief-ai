# OpsBrief AI

Turn structured operational events into daily briefs, risk warnings and incident summaries.

## Overview

OpsBrief AI is a small Python service. You send it operational events: a task
slipped, a shift went unfilled, an integration failed, a quality check was
rejected. It gives you back the things a duty manager actually needs:

- A daily operations brief.
- Risk warnings, each explaining which rule and which events triggered it.
- Incident timelines assembled from related events.
- Incident summaries.
- Suggested next actions.
- Source event IDs behind every generated statement.

Risk detection is deterministic and rule-based. Language models are used only
for summarising and phrasing, never for deciding what counts as a risk.

## Why This Project Exists

Operational tools are good at recording what happened and bad at telling you
what it means. A shift roster shows an empty slot. A ticket queue shows an
overdue item. An integration log shows a failed webhook. Nothing joins them up
and says: today's 18:00 fixture is short one steward, the same integration has
failed four times this week, and here is what to do first.

OpsBrief AI is that joining-up layer. It stays deliberately small: events in,
explainable summaries out, with every claim traceable to the events that
produced it.

## Current Capabilities

- FastAPI application with a `/health` endpoint reporting service name,
  version and environment.
- A validated operational event contract: `EventInput` for submissions and
  `Event` for stored events, with UTC-normalised timestamps and bounded
  metadata.
- SQLite persistence for events: a store that writes an event and reads it
  back unchanged, with UTC timestamps and typed metadata preserved.
- A `POST /events` endpoint that validates one submitted event, assigns it an
  identifier and stores it, recognising a resubmission carrying an
  `external_id` the same source has already sent rather than storing it twice.
- A `POST /events/batch` endpoint that validates a bounded batch of events and
  stores them together, all-or-nothing, recognising a resubmission carrying an
  `external_id` already seen from the same source rather than storing it twice.
- A `GET /events` endpoint that lists stored events newest first, filtered by
  source, type, severity or status and paginated with `limit` and `offset`.
- A `GET /events/{event_id}` endpoint that returns a single stored event, or
  404 when no event carries that identifier.
- Two sets of synthetic operational-event fixtures, loadable as validated event
  payloads: a general venue event day, and a sports-operations match day (short
  stewarding, an overdue pitch inspection, a blocked scoreboard task, a broadcast
  feed failing repeatedly, a rejected goal-line technology check and a
  crowd-density alert) for demos, documentation and Game Center readiness work.
- A deterministic risk contract and rule interface: a `Risk` that names the rule
  and the source event IDs behind it, a `RiskRule` protocol, and a `detect_risks`
  detector that runs a set of rules over stored events.
- An overdue-work rule that raises a risk for every event past its deadline and
  not yet resolved or cancelled, escalating from medium to high once the work is
  at least a day late, most overdue first.
- A blocked-work rule that raises a risk for every event a producer reported as
  blocked, with or without a deadline, escalating from medium to high once the
  work has been blocked for at least a day, longest blocked first.
- A repeated-integration-failure rule that raises a risk for every integration
  that has failed at least three times within the last week without recovering
  since, citing every failure behind it, high and escalating to critical for a
  larger run, most failures first.
- Deterministic priority scoring that ranks risks from different rules against
  each other: severity decides the order, the amount of evidence breaks ties, and
  the rest is settled by rule, title and event id, so the most pressing risk
  comes first whatever rule raised it.
- A `GET /risks` endpoint that runs every risk rule over the stored events and
  returns the current risks most urgent first, each naming the rule and source
  events behind it, with the reference instant the snapshot was judged against.
- An AI provider interface: a bounded `CompletionRequest`/`CompletionResponse`
  contract and an `AIProvider` protocol that turns already-assembled material into
  prose, used only for phrasing and never for deciding risks, with its output
  treated as untrusted data.
- A deterministic fake AI provider that returns scripted or echoed completions
  without calling a real model, and a `create_provider` factory that selects the
  provider named by `OPSBRIEF_AI_PROVIDER`, so tests and local runs are
  repeatable and offline.
- A deterministic daily-brief context: the material a brief is built from,
  assembled from the stored events without a model — the current risks in
  priority order, a bounded view of the most recent events, notes on where the
  picture is incomplete, and the source event IDs the whole picture traces back
  to.
- Structured daily-brief generation: `generate_brief` turns a context into a
  `DailyBrief` whose prose summary is phrased by the configured provider and
  whose risks, notes and source event IDs are carried over from the deterministic
  context, with the model's output constrained as untrusted data.
- A `GET /brief` endpoint that assembles the deterministic brief context over the
  whole stored event history and returns the current daily brief: a model-phrased
  summary alongside the prioritized risks, incompleteness notes and source event
  IDs the picture traces back to.
- An `opsbrief` command-line entry point that generates the current daily brief
  over the configured event store and prints it as a readable text block or as
  the brief's exact JSON, so a brief can be produced without running the server.
- Prompt and output version tracking on every generated brief: a `prompt_version`
  for the instructions and context rendering behind the summary and an
  `output_version` for the `DailyBrief` structure, stamped at generation so a
  brief traces to the exact prompt behind it and a consumer can detect a change
  in either.
- Graceful degradation when the AI provider fails: because the model only phrases
  a picture the service has already decided, a provider outage does not fail the
  brief or the `/brief` endpoint. The deterministic picture is still returned, the
  summary is left empty, a note records the outage, and the provider that was asked
  is recorded as the brief's model.
- An incident model with a deterministic status lifecycle: an `Incident` groups
  the source events behind one disruption and moves through `open`,
  `investigating`, `monitoring`, `resolved` and `closed` by allowed transitions
  only, recording when it opened, last changed and stopped being active, with a
  disallowed move refused rather than silently applied.
- Event linking on an incident: `link_events` and `unlink_events` attach and
  detach source events without reordering or duplicating the evidence or ever
  emptying it, refusing to change a closed incident, and `resolve_incident_events`
  turns an incident's cited IDs into the stored event records they name, in cited
  order, reporting any that no longer resolve.
- Incident timelines: `build_incident_timeline` lays an incident's cited events
  out in the order they occurred, oldest first, so a disruption reads forward in
  time, reporting the span it ran over and any cited ID that no stored event
  answers to.
- AI incident summaries: `generate_incident_summary` turns an incident and its
  timeline into an `IncidentSummary` whose prose is phrased by the configured
  provider and whose status, severity, span, cited events and missing-event notes
  are carried over deterministically, with the model's output constrained as
  untrusted data and a provider outage degrading to the deterministic picture
  rather than failing.
- Incident persistence: an `IncidentStore` that keeps declared incidents in
  SQLite, recording a declaration and saving each later change (a transition or
  an event link) so a tracked incident survives a restart, and reading them back
  by id or as a most-recently-opened-first listing filtered by status, with the
  ordered source event IDs preserved.
- Declaring incidents from stored events: `declare_incident_from_risk` opens an
  incident from a risk, carrying its title, mapped severity and cited events, and
  `declare_incidents_from_events` runs the canonical risk rules over the stored
  events and opens one incident per recognised risk, most urgent first, so the
  events a rule already grouped become a trackable incident without a model
  re-deciding what belongs together.
- Incident API endpoints: `POST /incidents` declares an incident from a posted
  title, severity and source events and stores it; `GET /incidents` lists stored
  incidents most recently opened first, filtered by status and paginated; and
  `GET /incidents/{incident_id}` returns a single stored incident, or 404 when no
  incident carries that identifier.
- Incident resolution notes: an incident can be resolved with an optional
  operator note explaining how it was put right, over
  `POST /incidents/{incident_id}/resolution`. The note is kept with the incident
  (absent while it is active, cleared if it reopens) and carried into the
  incident summary, so a reader sees how the disruption was resolved. Resolving an
  incident already past resolving is refused rather than silently reapplied.
- Sensitive-metadata redaction: a metadata value whose key names a sensitive
  term (a credential, an email, a phone number) is masked with a visible
  `[redacted]` marker before the event is stored, so it never reaches the
  database or a later read. The match is deterministic and rule-based, the key
  is kept so the masking is visible rather than silent, and the built-in term
  set is widened per deployment through `OPSBRIEF_REDACT_METADATA_KEYS`.
- Configurable AI context exclusion: a deployment can name event fields that are
  held back from the plain-text material a model is shown, on top of what
  redaction masks at storage. An excluded field is replaced by a visible
  `[excluded]` marker in the daily-brief and incident-summary material, so the
  model never sees it, while the deterministic picture a reader acts on (the
  risks, the source event IDs, the span) is unchanged. The fields are chosen
  through `OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS` and validated against the
  renderable set, so an unknown field fails loudly rather than leaking silently.
- Source references on generated output: alongside the flat `source_event_ids` a
  daily brief and an incident summary already carry, each generated output now
  resolves every cited id to a compact `SourceReference` describing what the event
  was (its source, type, subject, occurrence, severity and status), in the same
  order. The generated output is self-describing, so a reader does not look every
  cited event up separately, and a cited id no stored event answers to is carried
  as a visible unresolved reference rather than dropped. Resolution is
  deterministic and holds no model involvement.
- Confidence and missing-data warnings on generated output: a daily brief and an
  incident summary carry the gaps in their picture as structured `warnings`, each
  pairing a machine-readable code (no events, no risks, events omitted, missing
  events, no timeline, model unavailable, empty summary) with the same human
  message the notes show, and a `confidence` level (`high`, `medium`, `low` or
  `none`) derived from those warnings, so a reader can weigh the output at a glance
  and a consumer can branch on a code instead of parsing prose. The warnings and
  the confidence are deterministic and hold no model involvement.
- Structured generation audit records: a daily brief or an incident summary can be
  projected into a compact `GenerationAudit` naming what the output was produced
  from (its source event ids, and any cited id that no longer resolved) and by (the
  model that phrased it and the prompt and output versions), alongside the
  confidence and warning codes it reported. The record is a uniform provenance
  trail across both kinds of output, derived from an already-generated one, so it
  holds no model involvement of its own and never disagrees with the output it
  describes.
- A security policy and dependency scanning: `SECURITY.md` records how to report a
  vulnerability, which versions are supported and the design choices that keep the
  service safe, and `pip-audit` ships in the `dev` extra so the installed
  dependencies can be scanned for known advisories with one command.
- Environment-backed configuration via `OPSBRIEF_`-prefixed variables.
- Test suite and linting wired into GitHub Actions.
- Container image and Compose service for running the API without a local
  Python installation.

Nothing else is implemented yet. The roadmap below is a plan, not a
description of working software.

## Architecture

```
src/opsbrief/
  ai/           AI provider interface and the completion contract
  api/          FastAPI routers, one module per resource
  brief/        Daily-brief context assembly and generation
  events/       Operational event schema
  incidents/    Incident model and its status lifecycle
  risks/        Deterministic risk contract and rule interface
  samples/      Synthetic operational-event fixtures and their loader
  services/     Logic behind the routers
  storage/      SQLite connection handling and the event and incident stores
  cli.py        Command-line daily-brief generation
  config.py     Environment-backed settings
  main.py       Application factory and module-level `app`
tests/          Pytest suite mirroring the package layout
Dockerfile      Container image for the API
compose.yaml    Single-service Compose setup for local runs
```

The intended shape as the roadmap lands:

```
HTTP / webhook
      |
      v
  ingestion  -->  event store (SQLite)
                        |
             +----------+----------+
             |                     |
             v                     v
      risk rules            brief builder
   (deterministic)                 |
             |                     v
             |              AI provider interface
             |            (fake provider for tests)
             +----------+----------+
                        v
             briefs, risks, incidents
             each carrying source event IDs
```

Design constraints: one repository, one process, no message broker, no
background worker, no orchestration layer until something concrete requires it.

## Quick Start

```bash
git clone https://github.com/TomislavGreg/opsbrief-ai.git
cd opsbrief-ai

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

uvicorn opsbrief.main:app --reload
```

The API is then on http://127.0.0.1:8000, with interactive docs at
http://127.0.0.1:8000/docs.

Requires Python 3.12 or newer.

### With Docker

Docker needs no local Python installation. Requires Docker Engine 24 or newer
with the Compose plugin.

```bash
cp .env.example .env
docker compose up --build
```

The API is on http://127.0.0.1:8000 as above. The image installs the package
into `python:3.12-slim` and runs uvicorn as an unprivileged user. Compose passes
`.env` through as `OPSBRIEF_`-prefixed settings. The image declares a health
check against `/health`, so `docker compose ps` reports the container healthy
only once the API answers.

```bash
docker compose up -d --build   # Start in the background
docker compose ps              # Container and health status
docker compose logs -f api     # Follow logs
docker compose down            # Stop and remove
```

## API Examples

Check that the service is running:

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "service": "OpsBrief AI",
  "version": "0.1.0",
  "environment": "development"
}
```

Submit an operational event:

```bash
curl -X POST http://127.0.0.1:8000/events \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "rostering",
    "event_type": "shift.unfilled",
    "subject": "Steward shift for fixture 4821 is one short",
    "occurred_at": "2026-07-29T11:30:00+02:00",
    "severity": "high",
    "metadata": { "required": 4, "assigned": 3 }
  }'
```

The service answers `201 Created` with the stored event. It has gained the
`id` that later briefs, risks and incidents cite, and a `received_at`
timestamp, and `occurred_at` has been normalised to UTC:

```json
{
  "source": "rostering",
  "event_type": "shift.unfilled",
  "subject": "Steward shift for fixture 4821 is one short",
  "occurred_at": "2026-07-29T09:30:00Z",
  "severity": "high",
  "status": null,
  "entity_type": null,
  "entity_id": null,
  "due_at": null,
  "external_id": null,
  "metadata": { "required": 4, "assigned": 3 },
  "id": "9a9f05f9b99e402eb67a1a594eaa2339",
  "received_at": "2026-07-29T09:31:04.117382Z"
}
```

A payload that does not satisfy the event contract is answered with
`422 Unprocessable Entity`, naming the field at fault, and nothing is stored:

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "occurred_at"],
      "msg": "Value error, timestamp must include a timezone offset"
    }
  ]
}
```

Submit several events in one request:

```bash
curl -X POST http://127.0.0.1:8000/events/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "events": [
      {
        "source": "rostering",
        "event_type": "shift.unfilled",
        "subject": "Steward shift for fixture 4821 is one short",
        "occurred_at": "2026-07-29T11:30:00+02:00",
        "severity": "high"
      },
      {
        "source": "integrations",
        "event_type": "integration.failed",
        "subject": "Ticketing webhook failed again",
        "occurred_at": "2026-07-29T11:45:00+02:00",
        "severity": "medium"
      }
    ]
  }'
```

The service answers `201 Created` with a count and the stored events, each with
its own `id` and `received_at`:

```json
{
  "count": 2,
  "events": [
    { "id": "9a9f05f9b99e402eb67a1a594eaa2339", "subject": "Steward shift for fixture 4821 is one short", "...": "..." },
    { "id": "1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f", "subject": "Ticketing webhook failed again", "...": "..." }
  ]
}
```

A batch holds between 1 and 500 events. It is validated and stored as a whole:
if any event fails the contract the request is answered with `422` and nothing
is stored, and the insert is atomic, so a batch is never partly applied.
Resubmissions are recognised inside a batch exactly as they are for a single
event: an `external_id` the same source has already sent, whether stored by an
earlier request or repeated within this same batch, returns the previously
stored event in its place rather than creating a duplicate. The response returns
one event per submitted event, in order, and `count` reports how many were
newly stored — equal to the batch size when every event is new, and lower when
some were recognised as resubmissions.

List stored events, most recently occurred first:

```bash
curl 'http://127.0.0.1:8000/events?source=integrations&severity=high&limit=20&offset=0'
```

The service answers `200 OK` with a page of events and the total number of
matches, so a caller can tell whether more pages remain:

```json
{
  "total": 42,
  "limit": 20,
  "offset": 0,
  "events": [
    { "id": "1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f", "subject": "Ticketing webhook failed again", "...": "..." }
  ]
}
```

Every filter (`source`, `event_type`, `severity`, `status`) is optional and
matches its field exactly. `limit` defaults to 50 and holds between 1 and 500;
`offset` skips that many matches before the page begins. An unknown or
malformed query parameter is rejected with `422` rather than silently ignored.

Retrieve a single stored event by its identifier:

```bash
curl http://127.0.0.1:8000/events/9a9f05f9b99e402eb67a1a594eaa2339
```

The service answers `200 OK` with the stored event, exactly as a listing would
report it. An identifier that matches no stored event is answered with `404`,
naming the identifier, so a caller can tell a missing event from an empty one:

```json
{
  "detail": "no event is stored under id '9a9f05f9b99e402eb67a1a594eaa2339'"
}
```

A producer that includes an `external_id` can safely resend an event: the
first submission is stored and answered with `201 Created`, and a later
submission carrying the same `external_id` from the same `source` is recognised
as a resubmission. It is answered with `200 OK` and the originally stored event,
and nothing is stored again, so a delivery retried after a dropped connection
does not create a duplicate. The first submission wins: a resubmission that
reworded the same `external_id` still returns the event as first stored. An
event with no `external_id` carries no such key and is always stored. The key is
scoped to the `source`, so two producers may use the same `external_id` without
colliding. A `POST /events/batch` request recognises resubmissions the same way,
described above.

List the current operational risks, most urgent first:

```bash
curl http://127.0.0.1:8000/risks
```

The service answers `200 OK` with the risks recognised across the stored events,
each naming the rule and the source events behind it, and the reference instant
the snapshot was judged against:

```json
{
  "generated_at": "2026-07-29T18:00:00Z",
  "total": 2,
  "risks": [
    {
      "rule": "repeated_integration_failure",
      "title": "Integration ticketing has failed 5 times",
      "detail": "Integration \"ticketing\" (source: integrations) has failed 5 times ...",
      "severity": "critical",
      "event_ids": ["e17", "e18", "e19", "e20", "e21"]
    },
    {
      "rule": "overdue_work",
      "title": "Safety inspection for North Stand is overdue",
      "detail": "Work \"Safety inspection for North Stand\" was due at ...",
      "severity": "high",
      "event_ids": ["e04"]
    }
  ]
}
```

The endpoint takes no parameters: it always reports the whole current picture.
Risks are ordered by priority — severity first, then evidence, as described under
[Risk Detection](#risk-detection) — so the first risk is the one to act on first.
`total` counts the risks, and `generated_at` records when the snapshot was taken,
because a risk is judged against a moment in time.

Generate the current daily operations brief:

```bash
curl http://127.0.0.1:8000/brief
```

The service answers `200 OK` with a brief for the moment of the request: a
model-phrased `summary` alongside the deterministic picture behind it — the
prioritized `risks`, the `notes` on where the picture is incomplete, and the
`source_event_ids` every claim traces back to:

```json
{
  "generated_at": "2026-07-29T18:00:00Z",
  "summary": "One integration keeps failing and a safety inspection is overdue; deal with the ticketing failures first.",
  "model": "fake-1",
  "output_version": "daily-brief/3",
  "prompt_version": "brief-prompt/1",
  "confidence": "high",
  "risks": [
    {
      "rule": "repeated_integration_failure",
      "title": "Integration ticketing has failed 5 times",
      "detail": "Integration \"ticketing\" (source: integrations) has failed 5 times ...",
      "severity": "critical",
      "event_ids": ["e17", "e18", "e19", "e20", "e21"]
    },
    {
      "rule": "overdue_work",
      "title": "Safety inspection for North Stand is overdue",
      "detail": "Work \"Safety inspection for North Stand\" was due at ...",
      "severity": "high",
      "event_ids": ["e04"]
    }
  ],
  "notes": [],
  "warnings": [],
  "source_event_ids": ["e17", "e18", "e19", "e20", "e21", "e04"],
  "references": [
    {
      "event_id": "e17",
      "resolved": true,
      "source": "integrations",
      "event_type": "integration.failed",
      "subject": "Ticketing webhook failed",
      "occurred_at": "2026-07-29T14:05:00Z",
      "severity": "high",
      "status": "failed"
    }
  ]
}
```

The endpoint takes no parameters: it always reports the whole current picture.
Only the `summary` comes from a language model, and it is treated as untrusted —
collapsed to a single line and truncated to a bounded length — so injected
formatting or unbounded text cannot shape the brief. Everything a reader acts on
is carried from the deterministic context, as described under
[Daily Briefs](#daily-briefs). The active model is chosen by
`OPSBRIEF_AI_PROVIDER`; the default build phrases with the deterministic fake
provider, which reports itself as `fake-1`. The model is only a phrasing layer,
so it never fails the brief: when it returns no usable summary, or when the
provider is unavailable, the endpoint still answers with the deterministic
picture and a note recording which gap occurred, rather than an error. Wherever
the picture is incomplete or unphrased, the brief says so twice: `notes` in prose
and `warnings` as structured records a consumer can branch on, with `confidence`
summing those warnings into a single level (`high`, `medium`, `low` or `none`)
the brief can be weighed by, as described under
[Confidence and Warnings](#confidence-and-warnings). `output_version` names the
shape the brief was produced in and `prompt_version` the prompt that phrased its
summary, so a stored or piped brief stays interpretable and a change in either
stays visible.

Declare an incident to track:

```bash
curl -X POST http://127.0.0.1:8000/incidents \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Ticketing integration failing repeatedly",
    "severity": "high",
    "event_ids": ["e17", "e18", "e19"]
  }'
```

The service answers `201 Created` with the stored incident. It has gained the
`id` a caller reads it back by, its lifecycle `status` starts at `open`, and the
timestamps are set at declaration:

```json
{
  "id": "b3f1c2d4e5a6470897a1b2c3d4e5f6a7",
  "title": "Ticketing integration failing repeatedly",
  "status": "open",
  "severity": "high",
  "opened_at": "2026-07-29T18:00:00Z",
  "updated_at": "2026-07-29T18:00:00Z",
  "resolved_at": null,
  "event_ids": ["e17", "e18", "e19"],
  "is_active": true,
  "is_terminal": false
}
```

The body carries the parts a person decides: the `title`, the `severity` and the
source `event_ids` behind the incident. The service assigns the identifier and
the timestamps and starts the incident `open`, so those are not part of the
request, and a body that does not satisfy the contract (no events, a blank or
repeated id, an unknown field) is rejected with `422` and nothing is stored.

List tracked incidents, most recently opened first:

```bash
curl 'http://127.0.0.1:8000/incidents?status=open&limit=20&offset=0'
```

The service answers `200 OK` with a page of incidents and the total number of
matches, so a caller can tell whether more pages remain:

```json
{
  "total": 3,
  "limit": 20,
  "offset": 0,
  "incidents": [
    { "id": "b3f1c2d4e5a6470897a1b2c3d4e5f6a7", "title": "Ticketing integration failing repeatedly", "status": "open", "...": "..." }
  ]
}
```

The `status` filter is optional and matches the lifecycle state exactly; `limit`
defaults to 50 and holds between 1 and 500, and `offset` skips that many matches
before the page begins. A malformed filter or page parameter is rejected with
`422` rather than silently ignored.

Retrieve a single incident by its identifier:

```bash
curl http://127.0.0.1:8000/incidents/b3f1c2d4e5a6470897a1b2c3d4e5f6a7
```

The service answers `200 OK` with the stored incident, exactly as a listing
would report it. An identifier that matches no stored incident is answered with
`404`, naming the identifier, so a caller can tell a missing incident from an
empty one.

Resolve a tracked incident, recording how it was put right:

```bash
curl -X POST http://127.0.0.1:8000/incidents/b3f1c2d4e5a6470897a1b2c3d4e5f6a7/resolution \
  -H 'Content-Type: application/json' \
  -d '{ "note": "Restarted the ticketing sync and confirmed recovery." }'
```

The service answers `200 OK` with the incident moved to `resolved`, its
`resolved_at` set and the `resolution_note` recorded:

```json
{
  "id": "b3f1c2d4e5a6470897a1b2c3d4e5f6a7",
  "title": "Ticketing integration failing repeatedly",
  "status": "resolved",
  "severity": "high",
  "opened_at": "2026-07-29T18:00:00Z",
  "updated_at": "2026-07-29T19:30:00Z",
  "resolved_at": "2026-07-29T19:30:00Z",
  "resolution_note": "Restarted the ticketing sync and confirmed recovery.",
  "event_ids": ["e17", "e18", "e19"],
  "is_active": false,
  "is_terminal": false
}
```

The `note` is optional: a resolution with no note, or a blank one, still resolves
the incident and leaves `resolution_note` null. An identifier that matches no
stored incident is answered with `404`, and an incident that cannot move to
`resolved` (one already resolved or closed) is answered with `409` rather than
silently reapplied, so a caller can tell a missing incident from one already past
resolving.

Further endpoints are documented here as they are built.

## Event Schema

Producing systems submit events. The service assigns each accepted event an
`id` and a `received_at` timestamp, and every generated brief, risk and
incident refers back to those IDs.

| Field | Required | Notes |
|-------|----------|-------|
| `source` | yes | Producing system, for example `rostering`. |
| `event_type` | yes | Lowercase dotted name, for example `shift.unfilled`. |
| `subject` | yes | One-line human-readable description. |
| `occurred_at` | yes | When it happened. Must carry a timezone offset; stored as UTC. |
| `severity` | no | `info`, `low`, `medium`, `high` or `critical`. Defaults to `info`. |
| `status` | no | `open`, `in_progress`, `blocked`, `overdue`, `failed`, `resolved` or `cancelled`. |
| `entity_type`, `entity_id` | no | What the event is about. Supplied together or not at all. |
| `due_at` | no | Deadline attached to the work, when it has one. |
| `external_id` | no | The producer's own identifier, for recognising resubmissions. |
| `metadata` | no | Flat scalar detail, at most 25 entries. |

```json
{
  "source": "rostering",
  "event_type": "shift.unfilled",
  "subject": "Steward shift for fixture 4821 is one short",
  "occurred_at": "2026-07-29T09:30:00Z",
  "severity": "high",
  "status": "open",
  "entity_type": "fixture",
  "entity_id": "4821",
  "due_at": "2026-07-29T18:00:00Z",
  "metadata": { "venue": "North Stand", "required": 4, "assigned": 3 }
}
```

The contract is generic on purpose: domain specifics belong in `event_type` and
`metadata` rather than in bespoke fields. Timestamps without a timezone offset
are refused rather than guessed, and unknown fields are rejected so that a
mistyped payload fails loudly instead of being silently dropped.

Events reach storage through `POST /events`, shown above, or directly through
the store described below.

## Storage

Events are kept in SQLite, addressed by `OPSBRIEF_DATABASE_URL`. Only
`sqlite:///` URLs are accepted; anything else is refused at startup rather
than quietly falling back to a local file. `sqlite:///:memory:` gives a
throwaway database, which is what the tests use.

```python
from opsbrief.events import Event, EventInput, EventSeverity
from opsbrief.storage import EventStore

with EventStore.open("sqlite:///./opsbrief.db") as store:
    event = Event.from_input(EventInput(**submitted_payload))
    store.add(event)

    resend = Event.from_input(EventInput(**submitted_payload))
    kept = store.add_or_get(resend)  # The event stored under the resubmission key

    batch = [Event.from_input(EventInput(**payload)) for payload in submitted_batch]
    resolved = store.add_all_or_get(batch)  # New events stored, resubmissions returned as held

    stored = store.get(event.id)  # The stored event, or None
    recent = store.list_events(limit=50)  # Most recently occurred first
    failures = store.list_events(source="integrations", severity=EventSeverity.HIGH)
    total = store.count(source="integrations")  # Matches, ignoring pagination
```

The table is created on first use and the parent directory is made if it is
missing, so a fresh checkout runs with no setup step. Timestamps are stored as
fixed-width UTC text so that they sort in string order, and metadata is stored
as JSON, which keeps numbers, booleans and nulls the types they arrived as.
Storing an event under an identifier already in use raises
`DuplicateEventIdError` rather than overwriting stored history.

The running application opens the event store and the incident store when it
starts, both against the same configured database, and closes them when it
stops, so requests share a connection per store. Access is guarded by a lock,
because a SQLite connection is not safe to share across the threads FastAPI
runs synchronous handlers in. `list_events` and `count` take the same optional
column filters, so a filtered listing and its total stay in step. `add_or_get`
stores an event unless one is already stored under the same `(source,
external_id)`, in which case it returns that event; the lookup and the insert
run under the same lock, so two concurrent resubmissions cannot both be stored.
`add_all_or_get` applies that same recognition across a batch under a single
lock and transaction, deduplicating each event against both stored events and
earlier events in the same batch, so a resubmitted batch stays all-or-nothing
and never lands a duplicate. There is no object-relational mapper: nothing in
the roadmap yet needs one.

Incidents are kept the same way, in an `incidents` table addressed by the same
`OPSBRIEF_DATABASE_URL`. `IncidentStore` mirrors the event store's shape and
guards its connection with the same lock, but an incident is stateful where an
event is not, so writing and changing are kept apart: `add` records a newly
declared incident and refuses an identifier already in use, while `save`
overwrites one already stored with its current state, so a transition or an
event link is recorded whole, and refuses an incident that is not there rather
than silently declaring a fresh one. `get`, `list_incidents` and `count` read
them back, most recently opened first and optionally filtered by status. An
incident's ordered `event_ids` are stored as JSON, so its evidence round-trips
in the order it was linked.

```python
from opsbrief.incidents import Incident, IncidentSeverity, IncidentStatus
from opsbrief.storage import IncidentStore

with IncidentStore.open("sqlite:///./opsbrief.db") as store:
    incident = Incident.declare(
        title="Ticketing integration failing repeatedly",
        severity=IncidentSeverity.HIGH,
        event_ids=["e17", "e18", "e19"],
    )
    store.add(incident)

    working = incident.transition_to(IncidentStatus.INVESTIGATING)
    store.save(working)  # persist the state change

    store.get(incident.id)  # the stored incident, or None
    store.list_incidents(status=IncidentStatus.OPEN)  # most recently opened first
```

## Redaction

Producing systems put free-form detail in an event's `metadata`, and some of it
may be sensitive: a contact address, a phone number, a credential. This is a
public project that must never hold private or personal data, so a sensitive
value is masked before the event is stored rather than kept and hoped to stay
unseen.

Redaction is deterministic and rule-based, like risk detection: a metadata key
is sensitive when a configured term appears anywhere in its lowercased name, and
its value is then replaced by a visible `[redacted]` marker. The key itself is
kept, so a reader sees the field was present and masked rather than silently
dropped, and an absent (null) value is left as null since there is nothing to
hide.

```python
from opsbrief.redaction import redact_metadata

redact_metadata({"customer_email": "sam@example.com", "required": 4})
# -> {"customer_email": "[redacted]", "required": 4}
```

Masking happens at ingestion, so a sensitive value never reaches the database or
a later read: `POST /events`, `POST /events/batch` and the stores behind them all
return the redacted form. The built-in term set covers common credentials and
contact fields (`password`, `secret`, `token`, `api_key`, `email`, `phone`,
`ssn`, `credit_card` among them). A deployment widens it through
`OPSBRIEF_REDACT_METADATA_KEYS`, a comma-separated list of extra terms that adds
to the defaults rather than replacing them:

```bash
OPSBRIEF_REDACT_METADATA_KEYS="badge_number, seat"
```

Only `metadata` is redacted. The fields the service reasons over, such as
`subject` or `entity_id`, are the producer's own operational description and are
left as submitted, so producers should keep sensitive detail in `metadata` where
it can be masked.

## AI Context Exclusion

Redaction masks sensitive metadata values before an event is stored. Field
exclusion is a second, complementary control that narrows what a model may see
once an event is already stored: a deployment can name event fields that are held
back from the plain-text material a provider is shown, without touching the
stored event or the deterministic structured output a reader acts on.

The two controls are deliberately different. Redaction happens once, at
ingestion, and changes what is kept. Exclusion happens every time material is
rendered for a model, and changes only what the model is shown. The risks, the
source event IDs and the recent-events digest the service reasons over are
unchanged, so a brief or an incident summary still traces back to the same
evidence. Like redaction, exclusion keeps the field's label with a visible
`[excluded]` marker in the rendered material, so a reader of the prompt sees the
field was present and withheld rather than silently dropped.

```bash
OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS="subject, source"
```

The excludable fields are exactly those the brief and incident renderers describe
an event with: `source`, `event_type`, `subject`, `severity`, `status` and
`occurred_at`. An event's `id` and `metadata` are never rendered into that
material, so they are not excludable. A configured name that is not one of these
is refused when the settings are read, so a misconfiguration fails loudly at
wiring time rather than leaving a field the operator meant to hold back in the
model's view. The setting applies to both the daily brief (through `GET /brief`
and the `opsbrief` command) and incident summaries.

Exclusion narrows the recent-events view a model is shown, not the risks. A risk
title is a deterministic, rule-produced statement, not a raw event field, so it
is carried through unchanged: a reader acts on risks, and they are the point of
the brief. To keep a detail out of both, keep it in `metadata` where redaction
masks it, rather than in a field a rule reads.

## Source References

Every generated output traces back to the events behind it through a list of
source event ids. An id tells a reader which event to look up, not what it was. A
source reference closes that gap: it resolves an id against the stored events into
a compact descriptor, so the generated output is self-describing.

```python
from opsbrief.references import build_source_references

references = build_source_references(["e17", "gone"], events)  # events: stored Events
references[0].resolved  # True
references[0].subject  # "Ticketing webhook failed"
references[1].resolved  # False, no stored event answered to "gone"
```

A `SourceReference` always names the `event_id` it was built for and whether a
stored event `resolved` it. A resolved reference carries the fields a brief digest
or a timeline entry describes an event with (`source`, `event_type`, `subject`,
`occurred_at`, `severity` and `status`), not the free-form `metadata`, so it stays
as bounded as the digests it sits alongside. A cited id that no stored event
answers to becomes an unresolved reference with those fields left null, so a gap
in the evidence is stated plainly rather than passed over.

A daily brief and an incident summary both carry a `references` list next to their
flat `source_event_ids`: one reference per cited id, in the same order, so the two
stay in step. Resolution is deterministic and holds no model involvement, exactly
like the evidence it describes, so a reference never invents or reshapes what an
event was.

## Confidence and Warnings

A generated output is only as trustworthy as the material behind it. Some of the
picture may be missing (a cited event that no longer resolves, older events left
out because the view is bounded) or unphrased (the model was unavailable, or
returned nothing). A daily brief and an incident summary already carry `notes`
saying so in prose. Confidence and warnings state the same gaps in a form a
consumer can act on without parsing text.

```python
from opsbrief.warnings import Confidence, WarningCode

brief.warnings[0].code  # WarningCode.NO_RISKS
brief.warnings[0].message  # the same text the matching note carries
brief.confidence is Confidence.HIGH  # the level, derived from the warnings
```

Each `GenerationWarning` pairs a machine-readable `WarningCode` with the human
message the note beside it shows, so the two never disagree and a consumer can
branch on the code. The codes name one gap each: `no_events` and `no_risks` on a
brief, `events_omitted` when the recent-events view is bounded, `missing_events`
and `no_timeline` on an incident summary whose cited events no longer resolve, and
`model_unavailable` or `empty_summary` when the model did not phrase the picture.

`confidence` sums those warnings into a single level, derived from them rather than
stored, so it can never disagree with the gaps the output reports:

| Level | Meaning |
|-------|---------|
| `high` | No gap: the picture is complete and phrased. |
| `medium` | Partial or unphrased: some events omitted, or no model summary. |
| `low` | A gap in the cited evidence: some cited events no longer resolve. |
| `none` | No source data to describe: an empty store, or an incident whose cited events all vanished. |

An all-clear picture stays `high`: `no_risks` is good news, not a gap, so it does
not lower confidence. Both the warnings and the level are deterministic and hold
no model involvement, like the evidence they describe. Because the generated
output gained these fields, `GET /brief` reports `output_version` `daily-brief/3`
and an incident summary reports `incident-summary/3`.

## Generation Audit Records

A daily brief and an incident summary each carry their provenance in their own
shape: a brief covers the whole event store, a summary covers one incident, and the
two name their fields a little differently. A generation audit record is a single,
uniform account of that provenance, so a caller that wants to log or persist what
was generated, from what, and by what does not have to special-case each kind.

```python
from opsbrief.audit import audit_daily_brief, audit_incident_summary

brief_audit = audit_daily_brief(brief)  # brief: a generated DailyBrief
summary_audit = audit_incident_summary(summary)  # summary: an IncidentSummary

brief_audit.source_event_ids  # what the output was produced from, in citation order
brief_audit.missing_event_ids  # cited ids no stored event answered to at generation
brief_audit.model  # the model that phrased it
brief_audit.output_version, brief_audit.prompt_version  # the shape and prompt behind it
brief_audit.confidence, brief_audit.warning_codes  # how much of the picture stood
```

A `GenerationAudit` names its `kind` (`daily_brief` or `incident_summary`) and, for
a summary, the `subject_id` of the incident it describes. Every other field is
copied from the already-generated output: what it was produced *from* (the
`source_event_ids` it traces back to and the `missing_event_ids` a stored event no
longer answered to), what it was produced *by* (the `model`, `prompt_version` and
`output_version`), and how much of the picture stood (`confidence` and the
`warning_codes` the output reported). `source_event_count` is derived from the ids,
so it never disagrees with them.

The record is a projection, not a fresh judgement: it holds no model involvement of
its own and is a pure function of the output it describes, so the same output always
yields the same audit. The missing citations are read off the output's source
references (each cited id resolves to a reference, and the unresolved ones are
exactly the missing evidence), which is why a brief and a summary audit uniformly
despite carrying their references in different places.

## Security

The project's full security policy lives in [`SECURITY.md`](SECURITY.md): how to
report a vulnerability privately, which versions are supported, and the design
choices that keep the service safe. Several of those choices are described in
their own sections above, and they hold together as one posture: risk detection
is deterministic so a model never decides what matters, model output is treated
as untrusted data, every request body is validated, queries are parameterized,
sensitive metadata is redacted before storage, the material a model sees can be
narrowed, and no secrets live in the repository.

Dependencies are kept small and are scanned for known advisories with
[`pip-audit`](https://pypi.org/project/pip-audit/), which ships in the `dev`
extra. After installing the development dependencies, scan the environment:

```bash
pip install -e ".[dev]"
pip-audit
```

It checks the installed packages against the Python advisory database and names
any package with a known vulnerability alongside the version that fixes it. Run
it before a release and whenever a dependency is added or bumped, and upgrade an
affected package rather than leaving a finding open.

## Sample Data

The package ships two small sets of synthetic operational events, both
describing a single day of activity.

The general venue event day: unfilled shifts, an overdue safety inspection,
blocked work, a ticketing integration failing several times before it recovers,
a rejected quality check and a power alert.

```python
from opsbrief.samples import load_sample_events

events = load_sample_events()  # Validated EventInput models
```

The sports-operations match day, for Game Center readiness work: short
stewarding and an unfilled medic post, an overdue pitch inspection, a blocked
scoreboard calibration, a broadcast feed failing repeatedly without recovering,
a rejected goal-line technology check and a crowd-density alert. It is shaped so
the deterministic risk rules recognise it, so it doubles as material for risk and
brief demos, not just ingestion.

```python
from opsbrief.samples import load_sample_match_events

events = load_sample_match_events()  # Validated EventInput models
```

The fixtures are read from `src/opsbrief/samples/events.json` and
`src/opsbrief/samples/match_events.json` and validated through the same contract
producers submit against, so a fixture that drifts out of line with the schema
fails loudly rather than misleading a demo. Each event carries an `external_id`,
so a batch of them can be resubmitted without creating duplicates, and the two
sets use distinct ids so they can be loaded side by side. The data is entirely
fictional: this is a public repository and the fixtures contain no private,
customer or personal data.

## Risk Detection

Risks are recognised by deterministic rules, never by a language model. A rule
reads a batch of stored events and returns the risks it finds; a model may later
rephrase a risk, but it never decides that one exists. Every risk names the rule
that raised it and the source event IDs behind it, so a reader can trace the
claim back to the evidence.

```python
from opsbrief.risks import Risk, RiskRule, RiskSeverity, detect_risks

risks = detect_risks(events, rules)  # events: stored Events, rules: RiskRule instances
```

A `Risk` carries the `rule` that raised it, a `title` and `detail` explaining
it, a `severity` (`low`, `medium`, `high` or `critical` — a risk always
deserves attention, so there is no `info` level), and the `event_ids` behind
it. The model refuses to be built without a rule and at least one distinct,
non-blank source event, so a risk can never claim to exist without evidence.

A `RiskRule` is a small protocol: a stable `rule_id` and an `evaluate(events)`
that returns the risks the rule recognises, each tagged with that `rule_id`.
Rules are independent and deterministic — the same events always yield the same
risks — so `detect_risks` runs a set of them over one shared sequence of events
and collects what they raise, rule by rule, without mutating the events.

The first rule is `OverdueWorkRule`. Work is overdue when it carried a `due_at`
that has passed and is not yet resolved or cancelled; work exactly at its
deadline is not yet overdue. The rule is built with the reference instant it
judges against, so the same events at the same instant always yield the same
risks, and a test can pin the boundary exactly:

```python
from datetime import datetime, timezone

from opsbrief.risks import OverdueWorkRule, detect_risks

now = datetime.now(timezone.utc)
risks = detect_risks(events, [OverdueWorkRule(now)])
```

Each risk cites the single overdue event behind it. A risk is `medium` until the
work is at least a day late, when it escalates to `high`, and the risks come back
most overdue first.

The second rule is `BlockedWorkRule`. Work is blocked when its producer said so:
the rule trusts the stated `status` of `blocked` rather than inferring one, and a
deadline is not required — work that cannot move is a concern whether or not a
clock is running on it. Like the overdue rule it is built with the reference
instant it judges against, and it escalates by duration: a risk is `medium` until
the work has been blocked for at least a day, measured from when the event was
reported, when it escalates to `high`. Each risk cites the single blocked event,
and the risks come back longest-blocked first, ties broken by event id.

```python
from datetime import datetime, timezone

from opsbrief.risks import BlockedWorkRule, OverdueWorkRule, detect_risks

now = datetime.now(timezone.utc)
risks = detect_risks(events, [OverdueWorkRule(now), BlockedWorkRule(now)])
```

The third rule is `RepeatedIntegrationFailureRule`. A single failure is noise; the
same integration failing again and again is a risk. The rule groups failures by
the integration they name — an event whose `status` is `failed` and that carries
an `entity_id`, so it can be attributed — and raises a risk once one integration
has failed at least three times within the last week. A failure names its
integration through `entity_id`, so a failure with no entity is left to other
rules. A recovery (a `resolved` event for the same integration) that lands after a
run of failures clears it, the same way a `resolved` status clears overdue work,
so a manager sees integrations failing now rather than ones that already came
back. Each risk cites every failure behind it, oldest first; severity is `high`,
rising to `critical` for a run of five or more; and the risks come back
most-failures first, ties broken by the first cited event id.

```python
from datetime import datetime, timezone

from opsbrief.risks import (
    BlockedWorkRule,
    OverdueWorkRule,
    RepeatedIntegrationFailureRule,
    detect_risks,
)

now = datetime.now(timezone.utc)
rules = [OverdueWorkRule(now), BlockedWorkRule(now), RepeatedIntegrationFailureRule(now)]
risks = detect_risks(events, rules)
```

`detect_risks` gathers each rule's risks in the order the rules are given, which
is not an order of urgency: the overdue rule's risks precede the integration
rule's simply because it ran first. Ranking them against each other is
`prioritize`, a deterministic ordering that reads only the risks themselves:

```python
from opsbrief.risks import prioritize, priority_score

ranked = prioritize(risks)  # Most pressing first, whatever rule raised each
top = priority_score(ranked[0])  # Coarse priority, 1 (low) to 4 (critical)
```

Severity is the dominant signal — a `critical` risk always outranks a `high`
one, and no weight of evidence lifts a lower severity above a higher one.
`priority_score` is exactly that severity, as an integer from 1 to 4. Within a
severity the risk backed by more source events comes first, on the view that
more evidence means a more pressing concern; anything still tied is settled by
rule, then title, then first event id, so the order is total and never depends
on the order the risks arrived in. No language model takes part: like detection,
the ranking is a deterministic rule over the evidence.

The `GET /risks` endpoint surfaces exactly this: it runs the canonical rule set
over the whole stored event history at the moment of the request and returns the
prioritized risks. The reference instant is part of the answer, because a risk is
judged against a moment in time, and every risk still cites the rule and the
source events behind it. An example is shown under [API Examples](#api-examples).

## AI Providers

A language model has one job here: turning material the service has already
assembled into prose. It never decides what counts as a risk, how urgent
something is, or which events matter — those stay with the deterministic rules.
The provider interface reflects that narrow role and keeps every model behind a
single small seam, so the rest of the codebase depends on the contract rather
than on any one model, and a deterministic fake can stand in for a real provider
in tests.

```python
from opsbrief.ai import AIProvider, CompletionRequest, CompletionResponse

request = CompletionRequest(
    instructions="Summarise the operational picture in one line.",
    input="Two integrations failed; one safety inspection is overdue.",
)
response: CompletionResponse = provider.complete(request)  # provider: AIProvider
print(response.text, "—", response.model)
```

A `CompletionRequest` keeps the `instructions` (the task, phrased by the service)
apart from the `input` (the material to work on), so a provider can treat the
instruction as trusted framing and the input as data. The request is bounded on
purpose: `max_output_tokens` caps how much a model may return, `temperature`
defaults to zero because a stable phrasing is preferred over a varied one, and
both text fields are length-limited so a prompt cannot grow without bound.

A `CompletionResponse` carries the produced `text` and the `model` that produced
it, so a generated statement traces to its model just as a risk traces to its
rule. The text may be empty — an empty completion is a real outcome, not a
contract violation — and it is untrusted: a caller validates and constrains it
before use, exactly as it would any other external data.

An `AIProvider` is a small protocol: a stable `name` and a single
`complete(request)` method. A provider returns what the model produced and does
not judge it; when it cannot produce a usable completion — a transport failure, a
timeout, an unparseable reply — it raises `AIProviderError` rather than returning
an empty or invented one. Concrete providers, starting with a deterministic fake
for tests, implement this protocol in their own modules.

### The fake provider

Tests must never call a real model: real calls are slow, cost money and, worst of
all, are non-deterministic, so a test that asserted on their output would be
flaky. `FakeAIProvider` stands in with behaviour that is a pure function of the
request.

```python
from opsbrief.ai import CompletionRequest, FakeAIProvider

# Script exactly what the "model" returns, in order:
provider = FakeAIProvider(responses=['{"summary": "Two integrations failed."}'])
provider.complete(CompletionRequest(instructions="Summarise as JSON.")).text
# -> '{"summary": "Two integrations failed."}'

# Once the script runs out, it echoes the request's material, bounded and stable:
provider.complete(CompletionRequest(instructions="x", input="  many   spaces  ")).text
# -> 'many spaces'

provider.requests  # every CompletionRequest it received, in order
```

Scripted responses are returned verbatim, so a test can pin exactly what the
model "says" and exercise how the service parses and validates it. When the
script is exhausted the provider echoes the request's `input` (or its
`instructions` when there is no input), condensed to one line and truncated to
the request's `max_output_tokens`, so even the fallback honours the same output
bound a real provider would. Every request is recorded on `provider.requests`,
so a test can assert what the service actually asked for.

The active provider is chosen by configuration rather than hard-coded. Callers
ask `create_provider` for whatever `OPSBRIEF_AI_PROVIDER` names:

```python
from opsbrief.ai import create_provider

provider = create_provider()  # uses the application settings
```

Only the fake provider is implemented so far; an unknown name is refused with a
`ValueError` rather than silently ignored, so a misconfiguration fails loudly at
wiring time instead of producing empty briefs later.

## Daily Briefs

A daily brief is phrased by a language model, but the material behind it is
assembled first, deterministically, from the stored events. That assembled
material is a `BriefContext`, and building it is a pure function of the events
and the instant the brief is judged against — no model takes part, so the model
is only ever asked to phrase a picture the service has already decided.

```python
from datetime import datetime, timezone

from opsbrief.brief import build_brief_context

now = datetime.now(timezone.utc)
context = build_brief_context(events, now)  # events: stored Events

context.risks  # current risks, most urgent first
context.recent_events  # a bounded, newest-first view of recent activity
context.notes  # where the picture is incomplete
context.source_event_ids  # every event id the brief traces back to
```

The context gathers what a duty manager's brief needs to state. The current
risks come from the canonical rule set, judged over the whole event history and
ranked most urgent first, each still naming the rule and events behind it. The
recent-events view is a bounded digest of the most recent events, newest
occurred first, ties broken by event id so it is deterministic; it carries the
fields a brief describes an event with but not the free-form `metadata`, which
stays out of the context until a later phase governs what may be shown. `notes`
records where the picture is incomplete — no events recorded, no risks found, or
older events omitted because the view is bounded — so a brief can say so plainly
rather than imply completeness. `source_event_ids` collects every distinct event
the context draws on, risks before recent events, so the eventual brief traces
back to real evidence exactly as a risk does.

Risks are judged over the full history even though the recent-events view is
capped, so an overdue task from last week still raises its risk while the view
shows only today's activity. The cap keeps the context — and any prompt built
from it — bounded no matter how much history the store holds; it defaults to the
20 most recent events and is adjustable per call.

`generate_brief` turns that context into a `DailyBrief`. The model is shown the
context, rendered deterministically as plain-text material, and asked to phrase
the operational picture as a short summary:

```python
from opsbrief.ai import create_provider
from opsbrief.brief import build_brief_context, generate_brief

context = build_brief_context(events, now)
brief = generate_brief(context, create_provider())

brief.summary  # the picture in prose, phrased by the model
brief.model  # which model phrased it, for traceability
brief.output_version  # the shape the brief was produced in
brief.prompt_version  # the prompt that phrased the summary
brief.risks  # the current risks, carried over from the context
brief.notes  # where the picture is incomplete
brief.warnings  # the same gaps as structured, machine-readable records
brief.confidence  # how much of the picture stands, derived from the warnings
brief.source_event_ids  # every event id the brief traces back to
brief.references  # each of those ids resolved to what the event was
```

The division of labour is the whole point. The model contributes only the
`summary`, and its output is treated as untrusted: it is collapsed to a single
line and truncated to a bounded length before it is kept, so injected formatting
or unbounded text cannot shape the brief. Everything a reader acts on — the
prioritized `risks`, the `notes`, and the `source_event_ids` every claim traces
back to — is carried straight from the deterministic context, so the model can
rephrase the picture but never change what it says or invent an event. `model`
records which model produced the summary, so a generated statement traces to its
model just as a risk traces to its rule. Alongside it, every brief records the
version of the prompt that phrased its summary and the version of the output
structure it was produced in: `prompt_version` covers the instructions and the
context rendering, and `output_version` covers the `DailyBrief` shape. Both are
stamped by `generate_brief` from `BRIEF_PROMPT_VERSION` and `BRIEF_OUTPUT_VERSION`,
which are bumped when the prompt or the structure changes, so a change in phrasing
or shape is visible in the brief rather than silent. The model is a phrasing
layer, not the product, so it is never allowed to fail the brief. When it returns
no usable summary, or when the provider cannot produce one at all (a transport
error, a timeout, an unparseable reply), the brief is still produced from the
deterministic picture — with both versions still recorded — and a note records
which gap occurred. On a provider outage the brief records the provider that was
asked as its `model`, so even a degraded brief traces to where its summary should
have come from.

The `GET /brief` endpoint surfaces exactly this over HTTP: it assembles the
context over the whole stored event history at the moment of the request, phrases
it with the configured provider and returns the resulting `DailyBrief`. An
example is shown under [API Examples](#api-examples).

The same generation step is available on the command line, so a brief can be
produced without running the server:

```bash
opsbrief             # a readable text brief over the configured event store
opsbrief --format json   # the brief's exact JSON, the same shape GET /brief returns
```

The `opsbrief` command opens the event store named by `OPSBRIEF_DATABASE_URL`,
assembles the deterministic context over the whole history at the moment of the
run and phrases it with the provider named by `OPSBRIEF_AI_PROVIDER` — the same
store and provider the API uses. Text is laid out for a reader; `--format json`
emits the `DailyBrief` verbatim, so the two never disagree. An empty store still
produces a brief that plainly says there is nothing to report, rather than an
error.

## Incidents

A risk is recomputed from the current events every time it is asked for; an
incident is different. It is a stateful record of one disruption — a stretch of
related events worth tracking as a single thing — that is declared once and
moves through a lifecycle as the situation develops. The model and its lifecycle
are deterministic and hold no model involvement: a language model may later
phrase an incident summary, but it never declares an incident or moves it.

```python
from datetime import datetime, timezone

from opsbrief.incidents import Incident, IncidentSeverity, IncidentStatus

now = datetime.now(timezone.utc)
incident = Incident.declare(
    title="Ticketing integration failing repeatedly",
    severity=IncidentSeverity.HIGH,
    event_ids=["e17", "e18", "e19"],  # the events that triggered it
    at=now,
)

incident.status  # IncidentStatus.OPEN
working = incident.transition_to(IncidentStatus.INVESTIGATING, at=now)
resolved = working.transition_to(IncidentStatus.RESOLVED, at=now, note="Restarted the sync.")
resolved.resolved_at  # the instant it stopped being active
resolved.resolution_note  # "Restarted the sync."
resolved.is_active  # False
```

An incident carries the source `event_ids` behind it, distinct and non-blank, so
it traces back to real evidence exactly as a risk does. It records three instants:
`opened_at`, fixed when the incident is declared; `updated_at`, which advances on
every change; and `resolved_at`, set the moment the incident stops being active
and cleared again if it is reopened, so the resolution instant never disagrees
with the state. Alongside `resolved_at` it may carry a `resolution_note`, a short
operator explanation of how it was put right: it is attached when the incident
moves to an inactive state, kept when moving from `resolved` to `closed`, and
cleared on reopening, so like the instant it never disagrees with the state. A
note given on a reopening is refused, since an incident coming back is not being
resolved.

The lifecycle has five states. An incident is *active* while it is still being
worked — `open` (declared, unclaimed), `investigating` (actively worked) and
`monitoring` (mitigated, watched for recurrence) — and *inactive* once it has
stopped — `resolved` (believed fixed) and `closed` (signed off, terminal).
`transition_to` moves an incident only along an allowed edge: a resolved incident
may reopen for investigation if it recurs or be closed once signed off, but a
closed incident moves nowhere, and any disallowed move raises
`InvalidIncidentTransition` rather than being silently applied. Each move returns
a new incident, leaving the original untouched, so a caller can compare before
and after.

### Linking events

The events attributed to an incident are managed with `link_events` and
`unlink_events`, which follow the same immutable, deterministic shape as the
transitions:

```python
from opsbrief.incidents import resolve_incident_events

incident = incident.link_events(["e20", "e21"], at=now)  # a new failure joins
incident.event_ids  # ["e17", "e18", "e19", "e20", "e21"]
incident = incident.unlink_events(["e18"], at=now)  # attributed in error, removed
```

Linking appends only identifiers not already present, in the order given, so it
never reorders or duplicates the evidence and re-linking is a no-op; unlinking
ignores identifiers that are not linked. An incident must always cite at least
one source event, so an unlink that would remove the last is refused, and a
closed incident is a finished record whose evidence is frozen, so linking to or
unlinking from one raises `IncidentClosedError`.

An incident holds the identifiers of its events, not the events themselves.
`resolve_incident_events` turns those identifiers into the stored event records
they name, against any collection of events the caller supplies — typically the
current history:

```python
resolved = resolve_incident_events(incident, events)  # events: stored Events

resolved.events  # the cited events, in the incident's cited order
resolved.missing_event_ids  # cited IDs no stored event answered to
```

The events come back in the order the incident cites them, and every cited
identifier is accounted for exactly once — either as a resolved event or as a
missing ID — so a gap in the evidence is stated plainly rather than passed over.

### Declaring from events

An incident does not appear from nothing: it is declared from the events behind
one disruption. A risk already groups those events, so declaring an incident
from a risk carries that grouping forward into a stateful record without a model
and without re-deciding what belongs together. The risk's title, severity and
cited events become the incident's, so it traces back to exactly the events the
rule fired on.

```python
from opsbrief.incidents import declare_incident_from_risk, declare_incidents_from_events

incident = declare_incident_from_risk(risk, at=now)  # risk: a detected Risk
incident.status  # IncidentStatus.OPEN
incident.event_ids  # the risk's cited events, in cited order

incidents = declare_incidents_from_events(events, at=now)  # events: stored Events
```

`declare_incident_from_risk` maps one risk to a freshly opened incident, and
`declare_incidents_from_events` runs the canonical risk rules over the stored
events and opens one incident per recognised risk, ranked most urgent first so
the result reads in the same priority order the risks do. The risk severities map
one to one onto incident severities, both running `low` to `critical`. The
detection and every incident it seeds share one reference instant, so the same
events always yield the same incidents. Events that raise no risk produce no
incident. Nothing is stored: the functions return the incidents they open and
leave the caller to persist whichever it wants to track with `IncidentStore`.

### Timelines

An incident cites its events in the order they were linked, which is not
necessarily the order they happened. To read a disruption as a story a reader
needs them laid out in time. `build_incident_timeline` is that view: it resolves
the cited events against the stored records and orders the resolved ones by when
they occurred, oldest first.

```python
from opsbrief.incidents import build_incident_timeline

timeline = build_incident_timeline(incident, events)  # events: stored Events

timeline.entries  # the cited events, oldest occurred first
timeline.started_at  # when the first timeline event occurred, or None
timeline.ended_at  # when the last timeline event occurred, or None
timeline.missing_event_ids  # cited IDs no stored event answered to
```

Each entry is a stored event reduced to the fields a timeline describes it with,
carrying its `id` so a reader can look it up but not the free-form `metadata`,
for the same reason a brief's recent-events digest leaves it out. Ties on the
occurrence instant are broken by event id, so the order is total and does not
depend on the order the events arrived in. `started_at` and `ended_at` are
derived from the ordered entries, so they never disagree with them, and a
timeline with no resolved events has neither. The timeline builds on the same
resolution as `resolve_incident_events`, so a cited ID with no stored record is
reported in `missing_event_ids` rather than dropped, and every cited identifier
is accounted for exactly once, as either an entry or a missing ID.

### AI summaries

An incident timeline reads a disruption forward in time; an incident summary
reads it back as a short story: what happened, in what order, and where it stands
now. Like a daily brief, it divides its work strictly. The facts are assembled
deterministically from the incident and its timeline, and a language model is
asked only to phrase them.

```python
from opsbrief.ai import create_provider
from opsbrief.incidents import generate_incident_summary

summary = generate_incident_summary(incident, events, create_provider())

summary.summary  # the incident in prose, phrased by the model
summary.status  # where the incident sits in its lifecycle
summary.severity  # how serious it is
summary.resolution_note  # how it was resolved, when it carries a note
summary.started_at, summary.ended_at  # the span its cited events ran over
summary.source_event_ids  # the incident's cited events, in cited order
summary.references  # each cited id resolved to what the event was
summary.missing_event_ids  # cited IDs no stored event answered to
summary.notes  # where the picture is incomplete
summary.warnings  # the same gaps as structured, machine-readable records
summary.confidence  # how much of the picture stands, derived from the warnings
```

Only the `summary` comes from the model, and it is treated as untrusted: it is
collapsed to a single line and truncated to a bounded length, so injected
formatting or unbounded text cannot shape it. Everything else is carried straight
from the incident and its timeline, so the model rephrases the picture but never
changes what it says, never moves the incident, and never invents an event. The
`source_event_ids` are the incident's cited events in cited order, so a summary
traces back to the same evidence the incident does, and any cited ID that no
stored event answers to is carried in `missing_event_ids` and noted rather than
implied away. Every summary records the `model` that phrased it, the
`prompt_version` behind that prose and the `output_version` of its structure, so
a stored summary stays interpretable and a change in phrasing or shape stays
visible. The model is a phrasing layer, not the product, so it never fails the
summary: when it returns no usable text, or when the provider is unavailable, the
deterministic picture is still returned with an empty summary and a note recording
which gap occurred, and an outage records the provider that was asked as the
model.

### API endpoints

Incidents are declared and read over HTTP. `POST /incidents` declares an incident
from a posted title, severity and source events, assigns it an identifier and the
opening timestamps, starts it `open` and stores it. `GET /incidents` lists the
stored incidents most recently opened first, filtered by lifecycle status and
paginated, alongside the total match count. `GET /incidents/{incident_id}` returns
one stored incident, or 404 when no incident carries that identifier.
`POST /incidents/{incident_id}/resolution` moves a tracked incident to `resolved`
and records an optional note explaining how it was put right, saving the change;
it answers 404 when no incident carries the identifier and 409 when the incident
cannot move to `resolved` from its current state. The router stays thin: it
validates the request and hands the store to the service, which declares, reads
or resolves. The transition and note rules stay in the incident model, not the
router. The application opens the incident store alongside the event store when
it starts. Examples are shown under [API Examples](#api-examples).

## Development Commands

```bash
pytest                               # Full test suite
pytest tests/test_health.py          # One module
ruff check .                         # Lint
ruff check . --fix                   # Lint and autofix
ruff format .                        # Format
uvicorn opsbrief.main:app --reload   # Run the API locally
opsbrief                             # Print the current daily brief
opsbrief --format json               # Print it as JSON
```

```bash
docker compose up --build            # Build and run the API in a container
docker compose down                  # Stop it
docker build -t opsbrief-ai .        # Build the image on its own
```

## Roadmap

**Phase 0, Foundation.** Application skeleton, tooling, container setup, event
schema and SQLite persistence.

**Phase 1, Event ingestion.** Single and batch ingestion, retrieval, filtering,
pagination, duplicate protection and sample fixtures.

**Phase 2, Risk detection.** A deterministic, explainable rule interface, plus
rules for overdue work, blocked work and repeated integration failures, with
priority scoring and an API endpoint. No model involvement at this stage: every
risk names the rule and the events that raised it.

**Phase 3, AI daily briefs.** A provider interface with a deterministic fake
for tests, brief context assembly, structured brief generation, an API
endpoint, a CLI, and prompt and output version tracking. A brief states the
current operational picture, the highest-priority risks, relevant incidents,
suggested next actions, the source event IDs used, and where the data is
incomplete.

**Phase 4, Incident intelligence.** Incident model and lifecycle, event
linking, persistence, declaring incidents from related events, timelines, AI
summaries, API endpoints and resolution notes.

**Phase 5, Safety and explainability.** Field redaction, configurable AI
context exclusions, source references on generated output, confidence and
missing-data warnings, generation audit records and dependency scanning.

**Phase 6, Game Center readiness.** Authenticated webhook design, generic
webhook ingestion, sports-operations examples, an integration contract and
deployment documentation.

**Phase 7, Demo interface.** A server-rendered dashboard over the existing API,
started only once the API and core services are stable.

## Ticket Board

| ID | Ticket | Phase | Status |
|----|--------|-------|--------|
| AI-001 | Initialize FastAPI application and health endpoint | Foundation | Done |
| AI-002 | Add formatting, linting, tests and GitHub Actions | Foundation | Done |
| AI-003 | Add Docker setup and development commands | Foundation | Done |
| AI-004 | Define the operational event schema | Foundation | Done |
| AI-005 | Add SQLite event persistence | Foundation | Done |
| AI-006 | Update GitHub Actions to Node 24 compatible action versions | Foundation | Done |
| AI-010 | Add single-event ingestion endpoint | Event ingestion | Done |
| AI-011 | Add batch-event ingestion | Event ingestion | Done |
| AI-012 | Add event filtering and pagination | Event ingestion | Done |
| AI-013 | Add duplicate-event protection | Event ingestion | Done |
| AI-014 | Add sample operational-event fixtures | Event ingestion | Done |
| AI-015 | Add single-event retrieval endpoint | Event ingestion | Done |
| AI-016 | Recognise resubmissions within a batch | Event ingestion | Done |
| AI-020 | Define explainable risk-rule interface | Risk detection | Done |
| AI-021 | Detect overdue work | Risk detection | Done |
| AI-022 | Detect blocked operational work | Risk detection | Done |
| AI-023 | Detect repeated integration failures | Risk detection | Done |
| AI-024 | Add risk priority scoring | Risk detection | Done |
| AI-025 | Add risk-list API endpoint | Risk detection | Done |
| AI-030 | Define the AI provider interface | AI daily briefs | Done |
| AI-031 | Add deterministic test provider | AI daily briefs | Done |
| AI-032 | Build daily brief context from stored events | AI daily briefs | Done |
| AI-033 | Generate a structured daily brief | AI daily briefs | Done |
| AI-034 | Add daily brief API endpoint | AI daily briefs | Done |
| AI-035 | Add command-line brief generation | AI daily briefs | Done |
| AI-036 | Add prompt and output version tracking | AI daily briefs | Done |
| AI-037 | Degrade the daily brief when the provider fails | AI daily briefs | Done |
| AI-040 | Add incident model and status lifecycle | Incident intelligence | Done |
| AI-041 | Link operational events to incidents | Incident intelligence | Done |
| AI-042 | Generate incident timelines | Incident intelligence | Done |
| AI-043 | Generate AI incident summaries | Incident intelligence | Done |
| AI-044 | Add incident API endpoints | Incident intelligence | Done |
| AI-045 | Add incident-resolution notes | Incident intelligence | Done |
| AI-046 | Add incident persistence | Incident intelligence | Done |
| AI-047 | Declare incidents from stored events | Incident intelligence | Done |
| AI-050 | Add sensitive-field redaction | Safety and explainability | Done |
| AI-051 | Add configurable fields excluded from AI context | Safety and explainability | Done |
| AI-052 | Add source references to generated output | Safety and explainability | Done |
| AI-053 | Add confidence and missing-data warnings | Safety and explainability | Done |
| AI-054 | Add structured generation audit records | Safety and explainability | Done |
| AI-055 | Add security review and dependency scanning | Safety and explainability | Done |
| AI-056 | Run dependency scanning in CI | Safety and explainability | Blocked |
| AI-060 | Add authenticated webhook ingestion design | Game Center readiness | Backlog |
| AI-061 | Add generic webhook ingestion | Game Center readiness | Backlog |
| AI-062 | Add sports-operations example events | Game Center readiness | Done |
| AI-063 | Add Game Center integration contract | Game Center readiness | Backlog |
| AI-064 | Add match-operations daily brief example | Game Center readiness | Backlog |
| AI-065 | Add QC incident example | Game Center readiness | Backlog |
| AI-066 | Add deployment documentation | Game Center readiness | Backlog |
| AI-070 | Add simple server-rendered dashboard | Demo interface | Backlog |
| AI-071 | Display recent events | Demo interface | Backlog |
| AI-072 | Display active risks | Demo interface | Backlog |
| AI-073 | Display the latest daily brief | Demo interface | Backlog |
| AI-074 | Display incidents and timelines | Demo interface | Backlog |
| AI-075 | Add a public demo-data mode | Demo interface | Backlog |

Statuses: Backlog, Ready, In Progress, Review, Blocked, Done.

Phase 4 (Incident intelligence) is complete, and Phase 5 (Safety and
explainability) is complete apart from automating dependency scanning in CI:
sensitive metadata values are redacted before storage, a deployment can hold
configured event fields back from the material a model is shown, every generated
output resolves each cited event id to a descriptive source reference, a brief
and an incident summary now state how much of the picture is uncertain or missing
through structured warnings and a confidence level, a generated brief or summary
can be projected into a uniform audit record naming what it was produced from and
by, and the project now carries a security policy (`SECURITY.md`) and a
`pip-audit` dependency scan in the `dev` extra.

AI-056 (run dependency scanning in CI) is Blocked: it needs a change under
`.github/workflows/`, which the maintenance tooling cannot push, so a maintainer
applies it directly, as noted below. `pip-audit` can be run locally in the
meantime, as the Security section describes.

Phase 6 (Game Center readiness) is under way: the package now ships a
sports-operations match-day fixture alongside the general venue set, shaped so
the risk rules recognise it. The next steps build on it, such as a
match-operations daily brief example (AI-064). When a ticket's dependencies are
complete, promote it to Ready so the next change has a clear starting point.

### Maintaining the CI workflow

Files under `.github/workflows/` cannot be changed by the project's maintenance
tooling, which does not hold GitHub's `workflows` permission. Workflow edits are
applied by a maintainer directly. A ticket that needs one should say so, so that
it is not picked up and left half-finished.

## Recent Progress

- 2026-08-23 - Added a sports-operations match-day sample fixture alongside the general venue set: `load_sample_match_events` reads and validates a synthetic football match day (short stewarding, an unfilled medic post, an overdue pitch inspection, a blocked scoreboard task, a broadcast feed failing repeatedly and a crowd-density alert), shaped so the deterministic risk rules recognise it, giving Game Center readiness work realistic match-operations material.
- 2026-08-23 - Added a security policy and dependency scanning: `SECURITY.md` records how to report a vulnerability, which versions are supported and the design choices that keep the service safe, and `pip-audit` ships in the `dev` extra so the installed dependencies can be scanned for known advisories with one command. Automating the scan in CI is tracked separately as it needs a workflow change a maintainer applies.
- 2026-08-22 - Added structured generation audit records: a daily brief or an incident summary can be projected into a compact, uniform `GenerationAudit` naming what the output was produced from (its source and missing event ids) and by (its model and prompt and output versions), alongside the confidence and warning codes it reported, derived from the output and holding no model involvement of its own.
- 2026-08-21 - Added confidence and missing-data warnings to generated output: a daily brief and an incident summary carry the gaps in their picture as structured `warnings`, each pairing a machine-readable code with the message the note beside it shows, and a `confidence` level derived from those warnings, bumping the brief and incident-summary output versions.
- 2026-08-20 - Added source references to generated output: a daily brief and an incident summary now resolve every cited event id to a compact `SourceReference` describing what the event was, in the same order as their `source_event_ids`, with an unresolved reference for any cited id no stored event answers to, bumping the brief and incident-summary output versions.
- 2026-08-19 - Added configurable AI context exclusion: a deployment can hold named event fields back from the material a model is shown through `OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS`, replacing each with a visible `[excluded]` marker in the brief and incident-summary material while the deterministic picture a reader acts on stays unchanged.
- 2026-08-18 - Added sensitive-metadata redaction: a metadata value whose key names a sensitive term is masked with a visible `[redacted]` marker at ingestion, so it never reaches the store or a later read, with the built-in term set widened per deployment through `OPSBRIEF_REDACT_METADATA_KEYS`.
- 2026-08-17 - Added incident resolution notes: an incident can be resolved with an optional operator note over `POST /incidents/{id}/resolution`, kept with the incident (absent while active, cleared on reopening) and carried into its summary, with an older database gaining the new column on open.
- 2026-08-16 - Added incident API endpoints: `POST /incidents` declares an incident from a posted title, severity and events, `GET /incidents` lists stored incidents filtered by status and paginated, and `GET /incidents/{id}` returns one or 404s, with the incident store opened alongside the event store.
- 2026-08-16 - Added incident declaration from events: `declare_incident_from_risk` opens an incident from a risk, and `declare_incidents_from_events` runs the canonical risk rules over the stored events and opens one incident per recognised risk, most urgent first, without a model.
- 2026-08-15 - Added incident persistence: `IncidentStore` keeps declared incidents in SQLite, `add` records a declaration and `save` persists a later change, and `get`, `list_incidents` and `count` read them back, with the ordered source event IDs preserved as JSON.
- 2026-08-14 - Added AI incident summaries: `generate_incident_summary` turns an incident and its timeline into an `IncidentSummary` phrased by the provider and constrained as untrusted output, with status, severity, span, cited events and missing-event notes carried over deterministically and a provider outage degrading to the deterministic picture.
- 2026-08-13 — Added incident timelines: `build_incident_timeline` lays an incident's cited events out oldest occurred first, reports the span they ran over and any cited ID that no stored event answers to, without a model.
- 2026-08-12 — Made daily-brief generation degrade gracefully when the AI provider fails: an outage now returns the deterministic picture with an empty summary and a note, so the `/brief` endpoint answers rather than erroring.

## Future Game Center Integration

OpsBrief AI is a standalone open-source service and contains no private,
customer or personal data. It is built so that a separate operations platform
can later use it as its AI operations module.

The intended integration is one-directional and narrow. The platform posts
match, staffing, task, quality-control and integration events to an
authenticated webhook. OpsBrief AI stores them, applies its risk rules and
generates briefs and incident summaries. The platform reads those back over
the API. There is no shared database and no coupling to any platform-specific
schema: the event contract is generic, and sports-operations specifics arrive
as event types and metadata rather than as bespoke code paths.

That work is Phase 6. Nothing in the earlier phases assumes it.

## Contributing

Issues and pull requests are welcome.

- Branch from the latest `main` using `feat/`, `fix/`, `test/` or `docs/`
  followed by a short description.
- Run `ruff format .`, `ruff check .` and `pytest` before opening a pull request.
- Add or update tests for any changed behaviour.
- Keep changes focused: no unrelated refactoring in a feature pull request.
- Never commit secrets or real operational data.

See `CLAUDE.md` for the full set of development conventions.

## License

MIT. See `LICENSE`.
