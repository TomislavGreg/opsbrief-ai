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
- Environment-backed configuration via `OPSBRIEF_`-prefixed variables.
- Test suite and linting wired into GitHub Actions.

Nothing else is implemented yet. The roadmap below is a plan, not a
description of working software.

## Architecture

```
src/opsbrief/
  api/          FastAPI routers, one module per resource
  config.py     Environment-backed settings
  main.py       Application factory and module-level `app`
tests/          Pytest suite mirroring the package layout
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

Further endpoints are documented here as they are built.

## Development Commands

```bash
pytest                               # Full test suite
pytest tests/test_health.py          # One module
ruff check .                         # Lint
ruff check . --fix                   # Lint and autofix
ruff format .                        # Format
uvicorn opsbrief.main:app --reload   # Run the API locally
```

## Roadmap

**Phase 0, Foundation.** Application skeleton, tooling, container setup, event
schema and SQLite persistence.

**Phase 1, Event ingestion.** Single and batch ingestion, filtering,
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
| AI-003 | Add Docker setup and development commands | Foundation | Ready |
| AI-004 | Define the operational event schema | Foundation | Ready |
| AI-005 | Add SQLite event persistence | Foundation | Backlog |
| AI-006 | Update GitHub Actions to Node 24 compatible action versions | Foundation | Blocked |
| AI-010 | Add single-event ingestion endpoint | Event ingestion | Backlog |
| AI-011 | Add batch-event ingestion | Event ingestion | Backlog |
| AI-012 | Add event filtering and pagination | Event ingestion | Backlog |
| AI-013 | Add duplicate-event protection | Event ingestion | Backlog |
| AI-014 | Add sample operational-event fixtures | Event ingestion | Backlog |
| AI-020 | Define explainable risk-rule interface | Risk detection | Backlog |
| AI-021 | Detect overdue work | Risk detection | Backlog |
| AI-022 | Detect blocked operational work | Risk detection | Backlog |
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

### Blocked tickets

**AI-006.** CI currently warns that `actions/checkout@v4` and
`actions/setup-python@v5` target Node.js 20, which GitHub has deprecated and
now forces onto Node.js 24. Builds still pass, but the pinned versions should
be raised. This is blocked for automated maintenance: anything under
`.github/workflows/` requires GitHub's `workflows` permission, which the
maintenance tooling does not hold, so the change has to be applied by hand.

## Recent Progress

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
