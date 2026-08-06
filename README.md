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
- Environment-backed configuration via `OPSBRIEF_`-prefixed variables.
- Test suite and linting wired into GitHub Actions.
- Container image and Compose service for running the API without a local
  Python installation.

Nothing else is implemented yet. The roadmap below is a plan, not a
description of working software.

## Architecture

```
src/opsbrief/
  api/          FastAPI routers, one module per resource
  events/       Operational event schema
  risks/        Deterministic risk contract and rule interface
  samples/      Synthetic operational-event fixtures and their loader
  services/     Logic behind the routers
  storage/      SQLite connection handling and the event store
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

The running application opens one store when it starts and closes it when it
stops, so requests share a single connection. Access is guarded by a lock,
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
most overdue first. Ranking risks from different rules against each other is a
separate concern, handled by the priority scoring in a later ticket, along with
the API endpoint that surfaces the results. The blocked-work and repeated
integration-failure rules follow the same interface.

## Development Commands

```bash
pytest                               # Full test suite
pytest tests/test_health.py          # One module
ruff check .                         # Lint
ruff check . --fix                   # Lint and autofix
ruff format .                        # Format
uvicorn opsbrief.main:app --reload   # Run the API locally
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
linking, timelines, AI summaries, API endpoints and resolution notes.

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
| AI-022 | Detect blocked operational work | Risk detection | In Progress |
| AI-023 | Detect repeated integration failures | Risk detection | Backlog |
| AI-024 | Add risk priority scoring | Risk detection | Backlog |
| AI-025 | Add risk-list API endpoint | Risk detection | Backlog |
| AI-030 | Define the AI provider interface | AI daily briefs | Backlog |
| AI-031 | Add deterministic test provider | AI daily briefs | Backlog |
| AI-032 | Build daily brief context from stored events | AI daily briefs | Backlog |
| AI-033 | Generate a structured daily brief | AI daily briefs | Backlog |
| AI-034 | Add daily brief API endpoint | AI daily briefs | Backlog |
| AI-035 | Add command-line brief generation | AI daily briefs | Backlog |
| AI-036 | Add prompt and output version tracking | AI daily briefs | Backlog |
| AI-040 | Add incident model and status lifecycle | Incident intelligence | Backlog |
| AI-041 | Link operational events to incidents | Incident intelligence | Backlog |
| AI-042 | Generate incident timelines | Incident intelligence | Backlog |
| AI-043 | Generate AI incident summaries | Incident intelligence | Backlog |
| AI-044 | Add incident API endpoints | Incident intelligence | Backlog |
| AI-045 | Add incident-resolution notes | Incident intelligence | Backlog |
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

No tickets are currently blocked.

### Maintaining the CI workflow

Files under `.github/workflows/` cannot be changed by the project's maintenance
tooling, which does not hold GitHub's `workflows` permission. Workflow edits are
applied by a maintainer directly. A ticket that needs one should say so, so that
it is not picked up and left half-finished.

## Recent Progress

- 2026-08-05 — Added the overdue-work rule: it raises a traceable risk for every event past its deadline and not resolved or cancelled, escalating from medium to high once a day late.
- 2026-08-05 — Added the deterministic risk contract and rule interface: a `Risk` that traces back to its rule and source events, a `RiskRule` protocol and a `detect_risks` detector, ready for concrete rules to implement.
- 2026-08-04 — Added synthetic operational-event fixtures and a loader that validates them against the event contract, giving demos and later phases realistic sample data.
- 2026-08-03 — Extended resubmission recognition to `POST /events/batch`: a batch resubmitting a known `external_id`, or repeating one within itself, returns the stored event instead of creating a duplicate, and reports how many events were newly stored.
- 2026-08-02 — Added duplicate-event protection: a resubmission carrying a known `external_id` from the same source returns the originally stored event instead of storing it again.
- 2026-08-01 — Added the `GET /events/{event_id}` endpoint, returning a single stored event or 404 when the identifier is unknown.
- 2026-07-31 — Added the `GET /events` listing endpoint with source, type, severity and status filters and `limit`/`offset` pagination.
- 2026-07-30 — Added the `POST /events/batch` endpoint and an atomic bulk insert, storing a validated batch of events all-or-nothing.
- 2026-07-29 — Added the `POST /events` ingestion endpoint, the ingestion service and the application-owned event store.
- 2026-07-29 — Added SQLite event persistence: schema creation, an event store and its tests.
- 2026-07-29 — Raised the GitHub Actions versions to the Node 24 compatible majors, clearing the deprecation warning.
- 2026-07-29 — Added the operational event schema, its validation rules and tests.
- 2026-07-28 — Added the container image, Compose setup and Docker development commands.
- 2026-07-28 — Recorded the GitHub Actions Node 20 deprecation as AI-006 and documented why workflow changes need manual application.
- 2026-07-28 — Initialized the project: FastAPI application, health endpoint, settings, test suite, linting and CI.

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
