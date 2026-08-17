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
- A set of synthetic operational-event fixtures, loadable as validated event
  payloads, describing one event day at a venue for use in demos, documentation
  and later phases.
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
  "output_version": "daily-brief/1",
  "prompt_version": "brief-prompt/1",
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
  "source_event_ids": ["e17", "e18", "e19", "e20", "e21", "e04"]
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
picture and a note recording which gap occurred, rather than an error.
`output_version` names the shape the brief was produced in and
`prompt_version` the prompt that phrased its summary, so a stored or piped brief
stays interpretable and a change in either stays visible.

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

## Sample Data

The package ships a small set of synthetic operational events describing one
event day at a venue: unfilled shifts, an overdue safety inspection, blocked
work, a ticketing integration failing several times before it recovers, a
rejected quality check and a power alert. They give demos, documentation and
later phases realistic material without anyone hand-writing payloads.

```python
from opsbrief.samples import load_sample_events

events = load_sample_events()  # Validated EventInput models
```

The fixtures are read from `src/opsbrief/samples/events.json` and validated
through the same contract producers submit against, so a fixture that drifts out
of line with the schema fails loudly rather than misleading a demo. Each event
carries an `external_id`, so a batch of them can be resubmitted without creating
duplicates. The data is entirely fictional: this is a public repository and the
fixtures contain no private, customer or personal data.

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
brief.source_event_ids  # every event id the brief traces back to
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
resolved = working.transition_to(IncidentStatus.RESOLVED, at=now)
resolved.resolved_at  # the instant it stopped being active
resolved.is_active  # False
```

An incident carries the source `event_ids` behind it, distinct and non-blank, so
it traces back to real evidence exactly as a risk does. It records three instants:
`opened_at`, fixed when the incident is declared; `updated_at`, which advances on
every change; and `resolved_at`, set the moment the incident stops being active
and cleared again if it is reopened, so the resolution instant never disagrees
with the state.

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
summary.started_at, summary.ended_at  # the span its cited events ran over
summary.source_event_ids  # the incident's cited events, in cited order
summary.missing_event_ids  # cited IDs no stored event answered to
summary.notes  # where the picture is incomplete
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
one stored incident, or 404 when no incident carries that identifier. The router
stays thin: it validates the request and hands the store to the service, which
declares or reads. The application opens the incident store alongside the event
store when it starts. Examples are shown under [API Examples](#api-examples).

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
| AI-045 | Add incident-resolution notes | Incident intelligence | In Progress |
| AI-046 | Add incident persistence | Incident intelligence | Done |
| AI-047 | Declare incidents from stored events | Incident intelligence | Done |
| AI-050 | Add sensitive-field redaction | Safety and explainability | Backlog |
| AI-051 | Add configurable fields excluded from AI context | Safety and explainability | Backlog |
| AI-052 | Add source references to generated output | Safety and explainability | Backlog |
| AI-053 | Add confidence and missing-data warnings | Safety and explainability | Backlog |
| AI-054 | Add structured generation audit records | Safety and explainability | Backlog |
| AI-055 | Add security review and dependency scanning | Safety and explainability | Backlog |
| AI-060 | Add authenticated webhook ingestion design | Game Center readiness | Backlog |
| AI-061 | Add generic webhook ingestion | Game Center readiness | Backlog |
| AI-062 | Add sports-operations example events | Game Center readiness | Backlog |
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

No tickets are currently blocked. The next Ready ticket is AI-045 (add
incident-resolution notes): the incident endpoints from AI-044 now give it
somewhere to record a resolution. When a ticket's dependencies are complete,
promote it to Ready so the next change has a clear starting point.

### Maintaining the CI workflow

Files under `.github/workflows/` cannot be changed by the project's maintenance
tooling, which does not hold GitHub's `workflows` permission. Workflow edits are
applied by a maintainer directly. A ticket that needs one should say so, so that
it is not picked up and left half-finished.

## Recent Progress

- 2026-08-16 - Added incident API endpoints: `POST /incidents` declares an incident from a posted title, severity and events, `GET /incidents` lists stored incidents filtered by status and paginated, and `GET /incidents/{id}` returns one or 404s, with the incident store opened alongside the event store.
- 2026-08-16 - Added incident declaration from events: `declare_incident_from_risk` opens an incident from a risk, and `declare_incidents_from_events` runs the canonical risk rules over the stored events and opens one incident per recognised risk, most urgent first, without a model.
- 2026-08-15 - Added incident persistence: `IncidentStore` keeps declared incidents in SQLite, `add` records a declaration and `save` persists a later change, and `get`, `list_incidents` and `count` read them back, with the ordered source event IDs preserved as JSON.
- 2026-08-14 - Added AI incident summaries: `generate_incident_summary` turns an incident and its timeline into an `IncidentSummary` phrased by the provider and constrained as untrusted output, with status, severity, span, cited events and missing-event notes carried over deterministically and a provider outage degrading to the deterministic picture.
- 2026-08-13 — Added incident timelines: `build_incident_timeline` lays an incident's cited events out oldest occurred first, reports the span they ran over and any cited ID that no stored event answers to, without a model.
- 2026-08-12 — Made daily-brief generation degrade gracefully when the AI provider fails: an outage now returns the deterministic picture with an empty summary and a note, so the `/brief` endpoint answers rather than erroring.
- 2026-08-12 — Added event linking to incidents: `link_events` and `unlink_events` attach and detach source events without reordering, duplicating or emptying the evidence or touching a closed incident, and `resolve_incident_events` turns an incident's cited IDs into the stored event records they name.
- 2026-08-12 — Added the incident model and its status lifecycle: an `Incident` groups the source events behind one disruption and moves through `open`, `investigating`, `monitoring`, `resolved` and `closed` by allowed transitions only, refusing a disallowed move.
- 2026-08-11 — Added prompt and output version tracking to generated briefs: every `DailyBrief` records the `prompt_version` behind its summary and the `output_version` of its structure, so a brief traces to its prompt and a consumer can detect a change in either.
- 2026-08-11 — Added the `opsbrief` command-line entry point: it generates the current daily brief over the configured event store and prints it as a readable text block or as the brief's exact JSON, without running the server.
- 2026-08-10 — Added the `GET /brief` endpoint: it assembles the deterministic brief context over the whole stored event history and returns the current daily brief, a model-phrased summary alongside the prioritized risks, notes and source event IDs behind it.
- 2026-08-09 — Added structured daily-brief generation: `generate_brief` turns a context into a `DailyBrief` whose summary is phrased by the provider and constrained as untrusted output, with risks, notes and source event IDs carried over deterministically.
- 2026-08-09 — Added deterministic daily-brief context assembly: `build_brief_context` gathers the current risks, a bounded recent-events view, incompleteness notes and the source event IDs a brief traces back to, without a model.
- 2026-08-08 — Added a deterministic fake AI provider with scripted and echoed completions, and a `create_provider` factory that selects the provider named by `OPSBRIEF_AI_PROVIDER`.

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
