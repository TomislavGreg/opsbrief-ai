# Ticket backlog

Full bodies for the active tickets on the README board. The README holds the
board itself (IDs, one-line titles, phase and status); this file holds each
ticket's evidence, the minimal change intended, its dependencies and its
observable acceptance criteria. Completed tickets keep their one-line row on the
board and are not repeated here.

This backlog came out of a repository review (September 2026). The findings it
refers to (F01 through F26) are recorded alongside their fixes; the review file
itself is not committed. Priorities are project relative: P1 means an incorrect
operational result, a data-loss risk, an unsafe exposed boundary or a broken
supported startup path; P2 means a material reliability, speed, test or
maintenance improvement; P3 means a useful extension rather than a defect.
Effort is relative scope: S is a focused change, M is a few related code paths
plus behavioural verification.

For every code ticket: satisfy its acceptance criteria, add or update the
affected contract examples and prompt or output version identifiers where the
change needs it, keep the fast suite and Ruff green, review the diff, and put the
reproducing regression in the same pull request as the fix. Mark a ticket Done
only after the merged result is verified on CI.

## Dependencies and starting queue

Dependencies below are hard prerequisites, not a suggested reading order. The
README board holds the live status of every ticket; this section describes how the
queue moves, not a snapshot. A run selects the highest-priority eligible Ready
ticket whose dependencies are all Done. After a ticket is completed or blocked, the
run replenishes a small Ready queue by promoting the highest-priority eligible
Backlog items whose dependencies are Done, so the next run has work waiting. A
ticket blocked on one unavailable tool (for example AI-101 while Docker is
unavailable) is marked Blocked with the reason and owner and does not stall
unrelated eligible work.

At the last update the Ready queue was AI-099, AI-095 and AI-097; AI-099 was
promoted from Backlog now that AI-098 is Done, AI-097 became eligible once AI-096
was Done, and AI-095 once AI-094 was Done; AI-101 is Blocked on Docker
verification; AI-124 is Blocked on a maintainer settings action and AI-056 on a
workflow change. AI-092, AI-093, AI-094, AI-096 and AI-098 are Done. Read the
board, not this paragraph, for the current state.

A sensible progression:

1. Repair the P1 correctness, privacy, persistence and request-boundary bugs, and
   start the owner-managed CI and branch-protection work.
2. Complete startup validation, prompt completeness, performance, dependency
   reproducibility and operational backup and migration work; reorganise the docs
   and the routine instructions early enough to guide the rest of the board.
3. Add exact generation provenance, reporting periods and freshness, and the
   cross-component and package checks.
4. Finish the P3 extensions: the opt-in real provider, the incident brief section,
   retry-safe incident creation, incident change history, local cleanup and the
   dashboard drill-down.

An item is not complete just because a related feature already exists: its
acceptance criteria address the newly identified gap. Existing Done tickets stay
as historical records; these tickets correct or extend that behaviour without
rewriting the history.

## Correctness and safety

### AI-092: Evaluate current work state before raising blocked and overdue risks

Priority P1, Bug, effort M, Routine. Depends on: none. Finding F01. Status: Done
(reopened after a partial implementation, corrected; see "Reopened" and
"Resolved" below).

Evidence: a blocked or past-due event followed by a resolved event for the same
entity still raises both risks. The overdue and blocked rules classify individual
history entries independently, contrary to the producer contract, which tells
producers to submit later state changes (including resolution) for a stable
entity.

Minimal change: introduce one explicit work-state projection keyed by source,
entity type and entity id. Resolve its deterministic ordering at an evaluation
instant; leave the immutable events and the repeated-failure history intact. Treat
a non-state notification deliberately rather than letting a status-less event
erase known work state.

Acceptance criteria:

- Blocked to resolved and overdue to resolved or cancelled sequences (including a
  producer task-completed event carrying resolved status) stop the obsolete risks;
  reopening and a changed deadline produce the expected current result.
- Late arrival, equal occurrence timestamps and identical ids in different sources
  have documented deterministic behaviour. Missing entity data follows an explicit
  fallback.
- State selection and risk citations explain which event established the current
  condition; history stays retrievable.
- One table-driven behavioural suite covers those sequences through risk reporting
  and a generated brief. The integration example is updated to match.

Reopened: a first implementation landed (a work-state projection keyed by entity,
in `opsbrief/risks/work_state.py`, with the overdue and blocked rules judging the
entity's most recent event). Grouping by entity was the right shape, and the
clearing sequences above pass, but the implementation treats an informational
event as a full state replacement. It uses the single most recent event as the
current state, so any later event, even one that carries no status and no deadline,
overwrites the known state. Two defects follow, and both must become regressions in
the next implementation session before the fix:

- A task blocked for 48 hours with a past-due deadline correctly raises two
  high-severity risks (blocked and overdue). A later informational event for the
  same entity that carries no `status` and no `due_at` (for example a progress
  comment) wrongly clears both risks, because it becomes the current state and it is
  neither blocked nor past due. An informational event must preserve the known
  state, not erase it: the task is still blocked and still overdue.
- After that, a genuine "still blocked" report for the same entity wrongly resets
  the blocked duration to that report's time and lowers the severity from high back
  to medium, because duration is measured from the latest blocked event rather than
  from when the current unbroken block began. A re-affirmation of an existing block
  must not reset the continuous blocked duration or reduce severity.

Clarify for the fix: an event that carries neither a `status` nor a `due_at`
(nor any other field a rule reads) is informational and must leave the entity's
known state and its continuous blocked duration unchanged, rather than being taken
as the new current state. This is not a licence to ignore every status-less event:
the fix must distinguish a deadline that is simply omitted on an update (the prior
deadline still stands) from one a producer explicitly removes or replaces, and
must define that distinction rather than dropping every status-less event blindly.
Preserve the passing clearing behaviour and the immutable-history and
repeated-integration-failure guarantees. Do not write the fix or its tests in the
planning update that recorded this; they belong to a future implementation run.

Resolved: the rules now fold an entity's history into a projected current state
(`opsbrief/risks/work_state.py`) instead of reading only its latest event. An
event stating neither a `status` nor a `due_at` is informational and transparent:
it leaves the known status, the standing deadline and a continuous blocked run
untouched. A stated status or deadline updates the projection; an omitted deadline
on an update keeps the prior one; a terminal status ends the work and clears its
deadline, which is the one explicit removal as against a merely omitted one. The
blocked run is traced over each event's effective status, so a comment during a
block does not restart its clock or lower its severity, and its start is the report
that established the block. Overdue and blocked risks cite the event that set the
deadline and the one that began the block. Covered by unit tests
(`tests/test_risks_work_state.py`) and the behavioural suite through risk reporting
and a generated brief (`tests/test_risks_work_state_scenarios.py`).

### AI-093: Apply one evaluation instant and normalise iterable rule inputs

Priority P1, Bug, effort M, Routine. Depends on: the corrected AI-092 (Done).
Finding F02. Status: Done.

Resolution: a single occurrence-time boundary
(`opsbrief.risks.work_state.occurred_by`) now runs before the overdue, blocked and
repeated-integration-failure rules and the brief context, so an event dated after
the reference instant is a future report that takes no part in the present
snapshot: it cannot create or clear a present risk (a scheduled resolution, a
future recovery or a future reschedule no longer clears one) or appear as recent
activity, and advancing the reference admits it predictably. The boundary is on
occurrence time, not receipt time; receipt time only breaks ordering ties. The
integration recovery comparison was aligned with its own documentation and the
overdue rule (a failure at or after the most recent recovery still counts; only a
strictly later recovery clears it). One-shot iterables are materialised once in
`declare_incidents_from_events`, at the composition boundary, so a generator is not
exhausted by the first rule and yields the same declarations as the equivalent
list. This ticket does not introduce a bitemporal store.

Evidence: a future recovery clears three current integration failures; future
work enters today's context. The equal-time recovery prose disagrees with its
comparison. An iterator passed to incident declaration produces different results
from the equivalent list, because a generator is exhausted by the first rule.

Minimal change: apply one `as_of` boundary to state, failure and recovery, and
recent-activity selection. Materialise accepted one-shot iterables once at the
public composition boundary. Define occurrence-time versus receipt-time semantics
explicitly; do not turn this into a bitemporal database.

Acceptance criteria:

- Future events cannot create or clear a present risk or appear as past activity.
  Advancing `as_of` admits them predictably.
- A recovery exactly at a failure's occurrence instant follows one documented rule;
  a strictly later in-window recovery clears the earlier run. Timezone and
  seven-day-window boundaries are covered.
- Old unresolved work stays visible despite a short activity window; source and
  entity grouping stays isolated.
- Lists and equivalent generators produce identical risk and incident declarations
  without repeated consumption.

### AI-094: Enforce AI exclusions across all prompt material

Priority P1, Privacy bug, effort M, Routine. Depends on: none. Finding F03.
Status: Done. The masking, including the `incident_free_text` opt-out, is kept.
Deployment note: a real-data deployment should exclude `incident_free_text` unless
sending operator-authored titles and notes to an external provider is a deliberate
choice; the requirement to enforce that when a real provider is configured is
carried to AI-112.

Evidence: with `subject` excluded, an excluded marker still reaches the brief
prompt through a risk title, and the incident prompt through an incident title
derived from that risk. Excluding `occurred_at` still exposes it through the
incident span header. Field masking currently covers selected event and timeline
lines, not the whole prompt.

Minimal change: build a provider-safe projection before rendering, including safe
derived labels and dates. Do not use search-and-replace on the final prompt. Give
free-form incident title and resolution text their own documented policy. Preserve
the authorised structured output independently of this projection.

Acceptance criteria:

- A capturing fake receives none of an excluded field's synthetic marker through
  rows, titles, details, spans or notes derived from that field, across both the
  brief and incident paths.
- Every supported exclusion has an explicit prompt policy and a regression,
  including several exclusions together and none at all.
- Free-form incident text has a documented opt-out policy; arbitrary text
  replacement is not used as the privacy mechanism.
- Storage redaction still happens before persistence, structured references keep
  their contract, and the prompt-version identifier and docs reflect the changed
  material.

### AI-095: Budget prompt sections and disclose omitted evidence

Priority P2, Reliability bug, effort M, Routine. Depends on: AI-094. Finding F04.

Evidence: both renderers slice assembled material to 20,000 characters. With 120
blocked events only 89 risk lines reached the brief provider, warned only about
omitted recent events; a 120-event incident lost its resolution note, emitted no
omission warning and kept high confidence.

Minimal change: render prioritised complete sections into a declared budget.
Reserve room for current status, resolution and omission messages first; track the
visible event ids and omitted-item counts separately from the full structured
result.

Acceptance criteria:

- Large brief and incident fixtures stay within the limit and never end in a
  partial record; current status and resolution information survive prioritisation.
- Omitted risks, timeline events and other material produce accurate
  machine-readable warnings and matching completeness and confidence behaviour.
- Audit and context metadata distinguishes available evidence from evidence
  actually supplied to the provider.
- Empty, exactly-at-limit, large-Unicode and many-short-record fixtures behave
  deterministically. A real adapter may add its own stricter token-aware limit.

### AI-096: Make incident mutations atomic

Priority P1, Data-loss bug, effort M, Routine. Depends on: none. Finding F05.
Status: Done. Resolved by routing every incident mutation (resolve, transition,
link, unlink) through a new `IncidentStore.mutate`, which reads, applies the
change and writes it back while holding the store lock, so the read-modify-write
is one atomic step and interleaved mutations to one incident are serialised rather
than racing. The guarantee is scoped to the one shared store (a single connection
guarded by its lock) the application runs; separate connections to the same file
are not covered, which is documented on `mutate` and in the concurrency tests.

Evidence: two concurrent link requests read the same incident, add different event
ids, both report success, and only one addition is saved. The store lock covers
individual reads and saves; the service read-modify-write is unprotected.

Minimal change: perform read, domain mutation and save in one store transaction,
or use a revision check that returns a clear 409 on a stale write. Use one small
approach consistently across link, unlink, resolve and transition, including the
closed-record rule.

Acceptance criteria:

- Barrier-controlled concurrent links preserve both additions or return an explicit
  conflict; two success responses never conceal an overwritten edit.
- Concurrent link/unlink, resolve/transition and close/link combinations preserve
  the lifecycle and evidence rules.
- Failure rolls back the whole mutation; a rejected operation leaves the prior row
  unchanged.
- Tests use file-backed storage and reopen it to verify persisted outcomes, and
  document what is guaranteed across one and multiple connections.

### AI-097: Revalidate incident state and timestamps before persistence

Priority P2, Bug, effort S, Routine. Depends on: AI-096. Finding F06.

Evidence: resolving an incident with an explicit instant before it opened is
accepted and committed, then fails Pydantic validation on read-back. Mutation
methods use `model_copy(update=...)`, which does not revalidate.

Minimal change: construct a validated updated model, or validate all changed
invariants explicitly before committing. Normalise every supplied instant with the
same timezone rule.

Acceptance criteria:

- Mutations cannot regress `updated_at`; applicable timestamps satisfy
  `opened_at <= resolved_at <= updated_at`.
- Naive or backdated explicit times fail predictably before storage; aware
  non-UTC inputs normalise correctly.
- Every accepted transition, link and unlink can be serialised, stored and read
  back as a valid Incident.
- Linking an already-linked id or unlinking an absent id follows a documented no-op
  policy and does not invent a new modification timestamp.

### AI-098: Read reporting history from a stable SQLite snapshot

Priority P1, Correctness bug, effort M, Routine. Depends on: none. Finding F07.
Status: Done. Resolved by adding `EventStore.list_all_events`, which returns the
whole matching history in one ordered SELECT under a single hold of the store
lock, and reading the history through it instead of accumulating offset pages, so
a write can no longer land between two page reads and shift the newest-first
window under the reader. Added `EventStore.list_page`, which reads a page and its
total together under one lock hold, and assembled the `/events` listing through
it so a request's total agrees with its page. The guarantee is scoped to the one
shared store the application runs, as AI-096 is; the cross-request limitation of
public offset paging is documented on `EventQuery` and `list_page`, and left in
place because it is inherent to offset pagination.

Evidence: inserting a new newest event between the first and second 500-row pages
returned 502 rows with 501 distinct ids and omitted the new event. Stable ordering
does not make OFFSET paging stable across separate database snapshots.

Minimal change: replace internal whole-history page accumulation with one ordered
SELECT or an explicitly held read transaction or cursor. Define per-request list
and count consistency. Keep ordinary public offset pagination's cross-request
limitation explicit.

Acceptance criteria:

- Inserting through another connection during a controlled read yields one coherent
  before-or-after snapshot with no duplicate ids.
- Whole-history consumers see all rows in their snapshot, including histories above
  500 and exact page multiples.
- Relevant list totals and rows agree within the documented request semantics.
- The implementation does not silently cap history, and the tests do not need
  sleeps to expose the race.

### AI-099: Bound incoming bytes before parsing and handle malformed webhook bodies

Priority P1, Availability/input bug, effort M, Routine. Depends on: none. Finding F08.

Evidence: a body without `Content-Length` is fully consumed before the 8 MiB check
(a probe consumed 12 MiB before 413); a validly signed invalid-UTF-8 body returns
500 because only JSON decode errors are handled.

Minimal change: reject an excessive declared length before reading, enforce the
actual byte limit while streaming, and preserve the exact bounded bytes for the
signature. Map malformed encodings and JSON to a client error. Apply the same
byte policy to the other write paths (Pydantic limits apply only after parsing).

Acceptance criteria:

- Missing, misleading, invalid and excessive `Content-Length` values cannot bypass
  the actual byte limit; receipt stops at the cap plus at most one delivered chunk.
- Over-limit requests return 413 and persist nothing; malformed UTF-8 or JSON,
  including correctly signed malformed payloads, produce documented 4xx responses.
- The same request-size policy covers event, batch and incident writes without
  breaking their normal schemas.
- Tests cover chunked input, exact limits and multibyte Unicode. Docs distinguish
  encoded byte limits from event-count and field-character limits.

### AI-100: Keep synchronous webhook ingestion off the event loop

Priority P2, Performance/availability bug, effort S, Routine. Depends on: AI-099. Finding F08.

Evidence: the async webhook calls synchronous parsing and persistence directly; a
controlled 150 ms persistence delay pushed an unrelated coroutine scheduled for
10 ms to about 164 ms.

Minimal change: after a bounded async body read, run the expensive synchronous
parsing, validation and SQLite work through the framework's thread-pool facility.
Keep the success response after the transaction commits.

Acceptance criteria:

- A barrier-controlled persistence pause does not stop the loop from serving an
  independent lightweight operation.
- Valid batches stay atomic and response counts and idempotency match the current
  contract.
- Storage exceptions return the documented error rather than a premature success;
  cancellation and shutdown do not use a closed connection.
- No background queue, detached fire-and-forget write or new async database
  framework is introduced.

### AI-101: Give the container writable persistent SQLite storage

Priority P1, Deployment bug, effort S, Routine. Depends on: none. Finding F09.
Status: Blocked while Docker is unavailable to the routine.

Blocker: the acceptance criteria gate on a Docker-enabled run (a fresh image
starts as the non-root user and passes readiness, an ingested event survives a
container replacement through a mounted volume). The routine's environment has no
Docker, so the static Dockerfile, Compose and default-path change cannot be
verified and must not be merged unverified. Owner to unblock: the maintainer
running the container smoke check, or the routine running in a Docker-capable
environment. Once verification is possible, move it back to Ready.

Evidence: the image creates and copies `/app` as root, then switches to UID 1000;
the default database URL is relative and no writable data directory is created for
that user; Compose mounts no volume. Requires Docker-enabled verification.

Minimal change: create and own a dedicated data directory, point the default
container database there, and mount a named volume. Keep the non-root user.

Acceptance criteria:

- A fresh documented Compose setup starts as UID 1000 and passes readiness without
  a manual chmod.
- Ingest an event, replace the container, and retrieve the same event from the
  volume.
- A read-only or wrongly owned bind mount fails with an actionable startup error;
  the docs state ownership and backup paths.
- The fresh-image smoke path runs before closure and connects to AI-119 when that
  workflow exists.

### AI-102: Make external exposure and public demo writes safe by default

Priority P1, Deployment boundary, effort M, Routine. Depends on: none. Finding F10.

Evidence: with a webhook secret configured, an unsigned `POST /events` still
returned 201; incident mutations are also unauthenticated. Compose publishes the
port on all interfaces and demo seeding does not make the app read-only.

Minimal change: default Compose to loopback, add an explicit read-only mode for a
public demo, and document a reverse-proxy or ingress policy that exposes signed
ingestion while blocking internal write routes. Keep local development simple.

Acceptance criteria:

- Default Compose port publication is loopback-only; external exposure needs a
  deliberate configuration change.
- Read-only or demo mode refuses every mutation route, including batches, linking,
  transitions and webhooks, with consistent responses while reads still work.
- A tested example ingress exposes the intended signed route and blocks internal
  writes; it does not imply HMAC protects other routes.
- Private-data deployments have a clear read-access boundary. No account database
  or broad authentication product is required.

### AI-103: Validate configuration at startup and make readiness truthful

Priority P2, Reliability/maintenance, effort M, Routine. Depends on: none. Finding F11.

Evidence: an unknown provider serves readiness 200 then fails `/brief` with 500;
exclusion settings are parsed lazily; stores are opened before the lifespan cleanup
`try`; `log_level` is unused; readiness counts rows and exposes exception strings.

Minimal change: validate provider names and exclusion settings at startup without
paid network calls; acquire stores inside a cleanup scope (ExitStack); wire logging
once; use a cheap schema-aware readiness probe with safe public error categories.

Acceptance criteria:

- Unknown provider or exclusion settings fail startup with an actionable error and
  no network call; valid settings still support offline startup.
- If the second store open or seeding fails, every already-open resource is closed
  and partial application state is cleared.
- Readiness detects unavailable required storage or schema without a whole-table
  count and without leaking paths, credentials or arbitrary exception strings.
- The documented logging level affects logs; CLI configuration failures produce a
  concise actionable error and a non-zero exit rather than a traceback.

### AI-104: Align input validation with stored and generated output contracts

Priority P1, Input/read failure, effort M, Routine. Depends on: none. Finding F12.

Evidence: whitespace entity and external ids normalise to empty strings; infinite
metadata floats are accepted but serialise as null; blank incident titles and
unbounded evidence lists are accepted; a 65-character evidence id produced an
incident whose summary endpoint returned 500 because `SourceReference` allows 64.

Minimal change: share narrow field constraints where the contracts truly match.
Reject blank identifiers, non-finite numbers, blank titles and oversized evidence
collections. Check new evidence links against stored events; keep deliberate
unresolved-reference support when reading legacy records.

Acceptance criteria:

- Whitespace-only entity, external and incident-title values are rejected;
  entity-pair behaviour stays explicit.
- NaN and positive or negative infinity cannot enter stored metadata through
  direct, batch or webhook ingestion; valid scalars round-trip.
- Evidence-id length matches the Event and SourceReference limits; count limits
  apply to new requests and cumulative links, with an actionable 4xx and no partial
  mutation.
- Unknown ids in new declarations or links are rejected consistently; old
  missing-evidence records still render a documented warning instead of 500, and
  tests cover the policy change and compatibility.

### AI-105: Make timestamps and database paths round-trip reliably

Priority P1, Persistence bug, effort S, Routine. Depends on: none. Finding F12.

Evidence: an event dated year `0001` is accepted with 201, stored by
platform-dependent `strftime` as an unpadded year its parser cannot read, and later
event-list and brief reads fail with 500. Database setup expands `~` when creating
the parent directory but passes the unexpanded path to SQLite.

Minimal change: use one canonical fixed-width UTC representation for the supported
datetime range and normalise filesystem paths once. Preserve timestamp sort order
and old valid rows.

Acceptance criteria:

- The supported earliest and latest years, fractional seconds and timezone offsets
  round-trip through API to SQLite to API for events and incidents.
- Unsupported values, if the project chooses narrower bounds, are rejected before
  persistence across every writer.
- Previously stored non-canonical years are read or migrated safely, or reported
  with an explicit repair path; no silent deletion or timestamp guessing.
- Relative, absolute, tilde and in-memory database paths behave as documented, with
  no accidental creation at a different location.

## Efficiency and reporting

### AI-106: Reuse one reporting context per dashboard request

Priority P2, Performance/simplification, effort M, Routine. Depends on: AI-092, AI-093, AI-098. Finding F13.

Evidence: the dashboard separately builds a brief, recomputes risks, reads history
for incident timelines and queries recent events; the 1,001-event probe made ten
event-page queries.

Minimal change: build one request-scoped snapshot and deterministic context, then
pass the resulting risks, actions and events to the existing render and view
helpers. Reuse an event-id dictionary where needed.

Acceptance criteria:

- One dashboard request performs one intended whole-history read and one risk
  evaluation, with no duplicate provider call.
- Risk lists, actions, brief and incident previews agree on their declared snapshot
  and evaluation instant.
- Query and call-count tests demonstrate the removed repetition; output-order and
  filtering tests stay unchanged.
- Record before-and-after local benchmark methodology and results; ordinary CI
  asserts work or query growth rather than a wall-clock threshold.

### AI-107: Fetch incident evidence by id instead of scanning every event

Priority P2, Performance, effort M, Routine. Depends on: AI-098, AI-104. Finding F13.

Evidence: the timeline and summary services read all events even for one linked id.

Minimal change: add one parameterised `EventStore.get_many(ids)` operation,
chunking SQL placeholders when needed. Feed its results to the existing timeline and
reference builders and preserve explicit missing-id reporting.

Acceptance criteria:

- One-event incident retrieval does not enumerate unrelated history, including with
  10,000 unrelated events present.
- Empty, duplicate, missing and large id sets follow a documented ordering and
  dedup policy and stay within SQLite parameter limits.
- Timeline order, citation order and missing-evidence warnings keep their distinct
  behaviour.
- Query-count or plan checks show indexed lookup with cost governed by the requested
  evidence; no per-id N+1 loop replaces the full scan.

### AI-108: Bound risk lists and dashboard and timeline previews without dropping analysis

Priority P2, Performance/API usability, effort M, Routine. Depends on: AI-106, AI-107. Finding F13.

Evidence: risk output and dashboard rendering grow with every detected risk or
linked timeline entry despite limited recent-event and incident counts.

Minimal change: add validated pagination to the risk listing and bounded previews
with totals and continuations in the dashboard views. Keep generation material
bounded separately under AI-095 and keep the deterministic analysis complete.

Acceptance criteria:

- Stable priority and filter ordering, totals and limits apply to empty, small and
  large risk results; existing clients have a documented migration or version path.
- Dashboard risk and incident-timeline previews have explicit limits and accurate
  "showing X of Y" information.
- A critical or unresolved item cannot disappear from analysis because only a page
  was evaluated; tests place relevant evidence outside displayed pages.
- API and HTML response sizes scale with the requested display limits, and omitted
  display rows are distinguishable from missing evidence.

### AI-109: Enforce event idempotency in SQLite

Priority P2, Persistence hardening, effort M, Routine. Depends on: AI-104, AI-126. Finding F14.

Evidence: deduplication uses a per-instance check then insert; the
`(source, external_id)` index is not unique, so another connection can pass the
same check.

Minimal change: add a unique index for non-empty external ids and handle a
uniqueness conflict by returning the canonical existing event. Preserve the current
first-write-wins semantics.

Acceptance criteria:

- Two independent connections submitting the same source and external id
  simultaneously leave one row and receive the canonical event.
- Different sources stay independent; events with no external id stay separate;
  in-batch repeats keep their documented counts.
- A migration detects pre-existing duplicate keys and provides an explicit
  reconciliation report and path without silently deleting cited event rows.
- Transaction failures roll back the whole batch and no broad exception handler
  misclassifies an unrelated storage error as a duplicate.

### AI-110: Persist and retrieve the audit of an exact generation

Priority P2, Provenance/feature, effort M, Routine. Depends on: AI-094, AI-095, AI-098, AI-126. Finding F15.

Evidence: the brief and incident audit endpoints regenerate output, then project
that new output; the audit record cannot name the earlier output shown to a user.

Minimal change: add an immutable generation id and a compact SQLite generation
record, returned with the corresponding output and audit. Separate explicit
generation from retrieval; keep an intentional compatibility path for the current
GET endpoints.

Acceptance criteria:

- Fetching a saved generation or audit by id returns the exact original output and
  makes zero provider calls even after new events or settings changes.
- Record actual generation time separately from evaluation time, source and visible
  evidence, filters, versions, warnings and canonical input and output fingerprints.
- Raw prompts and excluded values are not stored by default; what the saved
  structured output legitimately contains is defined.
- Migration, unknown ids, provider failure, bounded listing and retention, and
  output-version compatibility have tests. GET reads do not silently grow audit
  storage.

### AI-111: Separate evidence completeness from prose verification and improve offline summaries

Priority P2, Trust/behaviour improvement, effort M, Routine. Depends on: AI-092, AI-093, AI-094, AI-095. Finding F16.

Evidence: a scripted provider returned "Everything is resolved; no work is blocked."
alongside a deterministic blocked risk, and the output kept high confidence. The
default fake echoes prompt text rather than composing an operational summary.

Minimal change: make completeness and narrative-verification status separate
explicit concepts. Add a short deterministic narrative from structured context for
the default offline mode; keep the scripted fake for tests. Present model prose with
an honest verification label.

Acceptance criteria:

- A deterministic blocked risk cannot be concealed by a model saying no work is
  blocked: structured status and actions stay visible and model prose is not
  labelled fact-verified.
- Offline summaries state the actual prioritised risk and incident picture, contain
  no raw prompt scaffolding and are stable for equal inputs.
- Contradiction, invented source ids, instruction-like event subjects and empty or
  outage replies have meaningful regression fixtures. A citation whitelist is not
  presented as semantic proof.
- API, dashboard, CLI and docs explain the distinction, with appropriate
  output-version changes. The existing fallback preserves structured evidence.

### AI-112: Add one opt-in real AI provider with bounded execution

Priority P3, New feature, effort M, Routine. Depends on: AI-094, AI-095, AI-103, AI-110, AI-111, AI-120. Finding F16.

Evidence: the factory currently supports only `fake`; this is a product extension,
not a claim that a real provider is broken.

Minimal change: implement one adapter using the existing provider protocol. Choose
the vendor and model explicitly when implementing and document the decision and the
current official API contract. Keep default operation offline, with configuration-only
opt-in.

Acceptance criteria:

- The adapter has explicit request and overall deadlines, bounded retries for
  transient failures, output and context limits, and cancellation and cleanup
  behaviour.
- Only AI-094's safe material is transmitted; secrets and raw operational prompts do
  not enter logs. Configuration validates before traffic is served.
- Mocked transport tests cover success, timeout, throttling, authentication failure,
  malformed responses and fallback. Ordinary CI never makes paid network calls.
- Provider and model identity, usage where available and versions reach the audit.
  The UI distinguishes model narrative from verified structured results, and a
  failure preserves deterministic output.
- Free-text policy (carried from AI-094): when this adapter sends real prompts to an
  external provider, a real-data deployment must exclude `incident_free_text` so an
  incident's operator-authored title and resolution note are held back, unless
  sending that operator text to the provider is a deliberate, accepted choice. The
  masking already exists (AI-094); this ticket must document the requirement where an
  operator configures the real provider (the provider setup docs and any example
  configuration) and default its examples to excluding `incident_free_text`. A
  synthetic offline demo, phrasing with the fake provider, may leave it shown. This
  is a documentation and configuration-default requirement, not a runtime-behaviour
  change to the masking.

### AI-113: Add reporting periods, source freshness and changes since a prior brief

Priority P2, New feature, effort M, Routine. Depends on: AI-092, AI-093, AI-106, AI-110. Finding F17.

Evidence: the brief evaluates stored history at now and includes a fixed number of
recent events; it does not express a business-day window, expected source freshness
or a delta since a prior brief.

Minimal change: introduce explicit period bounds and `as_of`, with an optional
comparison to a saved generation. Add source last-seen data and an optional
configured expected cadence. Share the small query model across API, CLI and
dashboard.

Acceptance criteria:

- A requested day or window selects activity accurately across timezone and
  daylight-saving boundaries while old unresolved work and needed integration
  history still affect risk.
- A quiet source and a source missing its configured expected update are represented
  differently; absent expectations never invent a stale warning.
- A comparison identifies new, cleared and changed risks using stable rule and
  entity identity and evidence, not fragile prose comparison; a missing or
  incompatible prior generation produces an explicit response.
- Period, evaluation instant, source filters and completeness are visible and saved
  with generation provenance; defaults stay simple and documented.

### AI-114: Include tracked incidents and recent resolutions in the daily brief

Priority P3, New feature/roadmap completion, effort M, Routine. Depends on: AI-095, AI-107, AI-111, AI-113. Finding F17.

Evidence: the roadmap calls for relevant incidents in the brief, but brief reporting
currently takes only the event store.

Minimal change: add a bounded deterministic incident section with current active
incidents and resolutions in the reporting period. Reuse targeted evidence
retrieval; keep model prose optional.

Acceptance criteria:

- The brief exposes relevant incident ids, status, severity, evidence and any
  resolution in the chosen period, in stable priority order.
- Linked risks and incidents are distinguishable without inflating counts or
  repeating the same next action unnecessarily.
- Empty, missing-evidence and large incident sets show accurate totals and omission
  warnings and stay within display and prompt budgets.
- API, CLI, dashboard and stored generation contracts agree; incident-only free text
  obeys AI-094's policy.

### AI-115: Make incident creation safe to retry

Priority P3, New feature, effort M, Routine. Depends on: AI-096, AI-104, AI-109, AI-126. Finding F14.

Evidence: repeating incident creation creates a new server id, so a lost response
can lead a client to duplicate the incident.

Minimal change: accept an optional client idempotency key with a defined scope and
store its request fingerprint and result atomically with creation. Leave no-key
calls as deliberate new incidents.

Acceptance criteria:

- Repeating the same key and canonical request returns the same incident, including
  concurrent requests and a retry after process restart.
- Reusing a key with different meaningful input produces a documented conflict, not
  silent acceptance of changed intent.
- Distinct or absent keys can create genuinely separate incidents even when titles
  or evidence overlap.
- Key length, retention, uniqueness and migration, and response-status semantics are
  documented and tested; no title-based fuzzy deduplication is introduced.

### AI-116: Record incident status and evidence changes

Priority P3, New feature, effort M, Routine. Depends on: AI-096, AI-097, AI-126. Finding F18.

Evidence: the incident row stores only current values; its timeline describes linked
operational events, not mutations of the incident record.

Minimal change: append a compact incident-change record in the same transaction as a
successful mutation. Add a paged read endpoint or view distinct from the operational
timeline.

Acceptance criteria:

- Declaration, transition, resolution and evidence additions or removals record what
  changed and when, without losing prior resolution information.
- Rejected or no-op mutations do not claim a change; rollback leaves neither a
  changed incident nor an orphan change record.
- Ordering is stable for equal timestamps, and history survives restart with bounded
  retrieval.
- Actor identity is optional and only trusted when supplied by an established
  authenticated boundary; arbitrary request text is not presented as verified
  identity.

### AI-117: Make demo timing explicit and seed atomically

Priority P2, Demo reliability bug, effort M, Routine. Depends on: AI-093, AI-101. Finding F19.

Evidence: the match fixture uses 12 September 2026 as its sample evaluation date and
its worked example does not reproduce at the review date. Seeding commits events
before the incident, so a failure between them leaves non-empty events and the next
startup skips repair.

Minimal change: keep fixed fixtures for tests; give live demo mode either a clearly
displayed fixed demo clock or one coherent time shift applied at initial seeding.
Seed the whole synthetic dataset atomically in one transaction.

Acceptance criteria:

- Tests using dates before and well after the fixture still produce the documented
  demo picture under the chosen explicit demo-clock policy.
- Event, deadline, receipt, incident and resolution timestamps stay coherent;
  ordinary non-demo reporting still uses the actual requested time.
- Injected failure between the events and the incident writes leaves no partial seed;
  restart is idempotent and detects existing incident data as well as events.
- Existing real data is neither overwritten nor mixed with a new seed; the dashboard
  clearly identifies synthetic data and its clock.

## Reliability, tests and operations

### AI-118: Add cross-component behavioural scenarios for the actual failure modes

Priority P2, Tests, effort M, Routine. Depends on: AI-092, AI-093, AI-094, AI-095, AI-096, AI-098, AI-104, AI-105, AI-111. Finding F20.

Evidence: the passing 883-test suite misses the interaction failures in F01 through
F12. Bug tickets already carry their own narrow regression.

Minimal change: add a small scenario layer using synthetic producer events, a
controlled clock and file-backed SQLite. Reuse a few readable fixture builders; avoid
a large testing DSL.

Acceptance criteria:

- Cover ingest, block or overdue, resolve or reopen, then brief and incident outputs,
  with an out-of-order arrival and a later process restart.
- Cover concurrent ingestion and reporting, and concurrent incident changes, with
  barriers, asserting durable evidence and counts.
- Cover exact provider input privacy and omission behaviour and degraded or
  contradictory narrative output through an API-facing scenario.
- Tests assert public behaviour and persisted results, not exact private helper calls
  except targeted query-growth checks; document which production risk each scenario
  guards.

### AI-119: Verify built packages and container startup in CI

Priority P2, CI/tests, effort M, Routine and maintainer. Depends on: AI-101, AI-103, AI-120. Finding F20.

Evidence: CI only installs editable source and runs style and tests. The README
documents a workflow-file permission blocker for the automation.

Minimal change: prepare executable package and container smoke commands, then have an
authorised maintainer wire them into Actions. Keep the fast suite separate and the
workflow steps readable.

Acceptance criteria:

- Build a wheel and sdist; install the wheel in a clean environment outside the source
  checkout and verify imports, CLI, API startup and packaged sample JSON.
- Build and start the image as its non-root user, wait with a fixed deadline for
  readiness, write synthetic data, replace the container and verify persistence.
- Failures print useful logs, clean up resources, and never wait indefinitely or
  require private or paying services.
- CI runs on the intended PR, head and main events with least privileges and green
  evidence for the installed workflow. If permission is unavailable, the prepared
  change stays reviewable and the workflow step stays Blocked with a named owner.

### AI-120: Make dependency resolution and compatibility maintenance repeatable

Priority P2, Dependencies/maintenance, effort M, Routine and maintainer. Depends on: none. Finding F21.

Evidence: runtime and dev dependencies specify lower bounds only, with no committed
reproducible resolution; CI tests one Python version against a fresh resolution; two
third-party TestClient and AnyIO deprecations remain.

Minimal change: choose one lightweight committed constraints or lock workflow for
reproducible development, CI and deployment. State supported Python and dependency
ranges; use grouped dependency-update PRs at a documented cadence. Prefer a small
configuration change over adopting a new toolchain.

Acceptance criteria:

- A clean install can reproduce the tested dependency set, and an intentional refresh
  has one documented command.
- CI checks the supported Python versions and verifies the declared minimum
  compatibility, or narrows the unsupported claims; it does not assert that untested
  minimums are broken.
- Third-party warnings are resolved through supported versions or tracked narrowly
  with rationale; no blanket warning suppression.
- Update PRs run the suite and any installed package or security checks, including
  AI-056 when available. Advisory triage distinguishes tool and runtime scope and
  environmental applicability.

### AI-121: Remove local duplication and simplify imports after behaviour is fixed

Priority P3, Code cleanup, effort S, Routine. Depends on: AI-094, AI-095, AI-106, AI-111. Finding F22.

Evidence: repeated shortening, summary and section helpers live in the three risk
rules and the brief and incident modules; sample re-exports use a late import and
`noqa: E402`; some long docstrings restate mechanics or overpromise behaviour.

Minimal change: extract only equivalent domain-local helpers, simplify the sample
imports and shorten redundant comments. Keep distinct render and projection
responsibilities explicit.

Acceptance criteria:

- Equivalent summary-normalisation and shortening policies have one clear
  implementation within an appropriate package; differently scoped policies stay
  distinct.
- Sample consumers use a clean import path without unnecessary circular re-exports or
  late-import suppression.
- Comments explain invariants and tradeoffs accurately and do not claim prose
  grounding, privacy or concurrency guarantees the code lacks.
- Existing behaviour tests pass; the diff introduces no generic service base classes,
  ORM, broad utility bucket or needless file reshuffle. No line-count target is used.

### AI-122: Reorganise README and documentation around first use and the active board

Priority P2, Documentation, effort M, Routine. Depends on: none. Finding F23.

Evidence: the README is about 2,580 lines, with quickstart near line 367, repeated
capability and progress narratives, and dozens of completed tickets mixed into the
working board.

Minimal change: keep one authoritative active board in the README; move completed
history and detailed ticket bodies into linked documents. Use the existing deployment
and integration documents as the owners of those contracts.

Acceptance criteria:

- The README presents purpose, current implementation status, quickstart, a minimal
  example, architecture, the active board and a short documentation map near the top.
  A newcomer can run the documented first-use path without reading the ticket archive.
- Completed tickets and history are preserved in `docs/history.md`; full acceptance
  criteria and dependencies live in `docs/tickets.md`; active statuses stay in the
  README only.
- Exhaustive API, AI and operations explanations move to focused documents, duplicate
  schema prose is replaced with selected examples or OpenAPI links, and the inaccurate
  claims mapped in the review are fixed. Pending fixes are described honestly until
  merged.
- Internal links and executable examples are validated; CLAUDE entry links are
  updated; AI-056's blocker and owner stay visible. Future feature PRs update the
  relevant document rather than duplicating full narratives.

### AI-123: Give the routines explicit ticket selection, completion and stop rules

Priority P2, Automation/maintenance, effort M, Routine and maintainer. Depends on: AI-122. Finding F24.

Progress: the in-repo half of this ticket is drafted. The reusable routine
instruction set is [`docs/routine.md`](routine.md), linked from `CLAUDE.md`, and
covers selection, the Ready queue, one-ticket-at-a-time work, verification on the
actual PR-head and merged-main commits, marking Done only after verification,
respecting permissions and recording blockers, and avoiding filler commits and
repetitive progress narratives. What remains keeps this ticket open: the external
routine configuration (the scheduled prompt the run fires from) must be reconciled
with `docs/routine.md` by its owner, and the maintainer must confirm the live
routine implements these rules and respects the workflow and settings permissions.
A prepared instruction file in the repository does not by itself certify the unseen
live routine.

Evidence: an exhausted board, frequent status-related commit subjects and the
documented workflow permission blocker. The external live routine definitions were
not accessible during review.

Minimal change: publish a concise reusable routine instruction set in the repository
and reconcile the external routines with it through their owner. Keep one eligible
ticket in progress and use the existing PR and rebase workflow.

Acceptance criteria:

- Select the highest-priority eligible Ready ticket with completed dependencies; if
  there is none, report that state and stop rather than inventing work. Mark blocked
  work with a reason and next responsible owner.
- A bug task starts with a reproducible failure and ends with its regression, the
  relevant docs and version changes, a reviewed diff and passing fast checks. A
  feature task starts from its acceptance criteria.
- GitHub checks use authenticated access, target the actual PR head and merged commit,
  and have bounded waiting and retry behaviour. Failed, cancelled or missing runs do
  not count as success.
- Done follows a verified merge. Necessary status updates are batched; quota-driven
  commits and repeated capability narratives are avoided. Prompt, render and output
  contract changes have an explicit version-update check.
- The maintainer confirms the external routine prompts implement these rules and
  respect the workflow and settings permissions. A prepared instruction file alone
  does not certify an unseen live routine.

### AI-124: Enforce the PR and CI gate on main

Priority P2, Repository governance, effort S, Maintainer. Depends on: none. Initial status Blocked. Finding F24.

Evidence: GitHub reported `main` unprotected and no repository rulesets on 7 September
2026; CI exists but is not enforced by those settings.

Minimal change: configure a branch rule or ruleset requiring PR-based changes and the
actual CI check names, with an explicit trusted review policy compatible with the
owner's workflow. Keep automation permissions least-privileged.

Acceptance criteria:

- An ordinary automation identity cannot directly push around the PR requirement or
  merge a failing or missing required check.
- Required checks match the real workflow job names; updating checks does not leave
  PRs waiting on obsolete names.
- Any bypass authority is deliberately limited and documented; routine credentials do
  not gain broad settings or workflow permissions as a workaround.
- Enforcement is verified with a small controlled PR and the settings and evidence are
  recorded. Until the authorised owner applies the setting, this is Blocked, not Done.

### AI-125: Add safe backup and restore diagnostics and a small release checklist

Priority P2, Operations/maintenance, effort M, Routine. Depends on: AI-101, AI-103. Finding F25.

Evidence: the deployment docs cover backups, but the shipped CLI lacks an integrated
stdlib backup and verification path; there were no tags or releases at review time.

Minimal change: add focused CLI subcommands using SQLite's backup API plus integrity,
schema and version checks. Document an offline restore path and a release checklist;
keep Python's stdlib sufficient for normal backup operation.

Acceptance criteria:

- Back up a database while the application can read and write it, restore into a new
  offline target, and verify representative event and incident records and integrity.
- Never overwrite an existing restore destination without an explicit operator choice;
  partial outputs and error messages are handled predictably.
- Diagnostics identify application and schema versions and database readiness without
  printing secrets or operational payloads; destructive pruning is not scheduled
  automatically.
- The release checklist covers a clean artifact install, matching package and health
  version, dependency evidence, upgrade and backup notes and an intentional changelog
  and tag. Recovery steps are documented in the actual container data path.

### AI-126: Version SQLite schema upgrades and test old databases

Priority P2, Database maintenance, effort M, Routine. Depends on: AI-125. Finding F25.

Evidence: schema creation currently adds missing columns from a short list; the
planned unique index and generation and change tables need ordered upgrades and
existing-data handling.

Minimal change: use a small numbered migration list and a SQLite schema version, with
explicit transactional behaviour. Keep direct SQL rather than introduce a migration
framework.

Acceptance criteria:

- Fixtures for the original schema and the current schema upgrade to the intended
  version while preserving events, incidents, linked ids and resolution notes.
- Upgrades are restart-safe, ordered and transactional where SQLite permits; a failure
  does not falsely advance the version. `executescript` transaction behaviour is
  accounted for explicitly.
- Opening an unknown newer schema refuses unsafe writes with an actionable error; the
  documented backup procedure precedes upgrade.
- Constraint conflicts produce a report and a deliberate repair path, not silent
  evidence deletion. Future tickets add migrations through this same mechanism.

### AI-127: Add dashboard evidence links and basic accessibility

Priority P3, UX improvement, effort S, Routine. Depends on: AI-108, AI-113. Finding F26.

Evidence: server-rendered rows expose useful ids and data but lack a smooth path to
individual evidence and incident detail, and long tables need clearer narrow-screen
behaviour.

Minimal change: add safe relative internal links to event, incident and timeline
detail; make partial, empty and stale states clear; improve table overflow and
keyboard navigation using the HTML and CSS already in the project.

Acceptance criteria:

- Source references and incident entries lead to the correct record or timeline; a
  missing record shows a useful state instead of a broken-looking action.
- Preview totals and continuations match AI-108; reporting period, synthetic or demo
  clock and freshness information are visible where relevant.
- Headings, links and tables have meaningful semantics and focus behaviour, and long
  values are usable on a narrow viewport.
- Escaping stays intact for titles, notes and ids. Rendering tests assert link targets
  and state messages; no front-end framework or brittle whole-page snapshots are
  needed.

### AI-056: Complete dependency scanning in CI (existing ticket)

Priority P2, Security maintenance/CI, effort S, Maintainer. Depends on: AI-120. Blocked. Finding F21.

Evidence: AI-056 is already Blocked on the board; CI currently has no audit step.
Reuse this ticket rather than create a second scanner task.

Minimal change: prepare a `pip-audit` check against the intended installed or locked
dependency scope, then have an authorised maintainer add it to the workflow. Use the
existing dev tool, with documented advisory triage.

Acceptance criteria:

- The scanner runs in the intended CI context and reports dependency names and
  versions plus distinct advisory ids and fixes, with clear runtime versus tooling
  scope.
- A controlled vulnerable-dependency fixture or isolated verification exercise
  demonstrates the failure gate without adding a vulnerable dependency to main.
- Network or database failures are distinguishable from clean scans; approved
  exceptions are specific, justified and expire. Duplicate advisory records are not
  counted as separate vulnerabilities.
- Required permissions are satisfied through the authorised owner; green evidence for
  the actual workflow commit is recorded before Blocked becomes Done.
