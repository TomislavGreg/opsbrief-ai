# Maintenance routine

How a run advances this repository. A run picks up one ticket from the board,
implements it against its acceptance criteria, and merges it through a pull
request. This file is the standing instruction set; it does not replay any past
session.

## Where to start each run

Resume from the current state of the repository, not from an earlier
conversation. Read, in order:

1. The README Ticket Board: the live status of every ticket.
2. [`docs/tickets.md`](tickets.md): the full body of each active ticket, with its
   evidence, intended change, dependencies and acceptance criteria.
3. The dependencies and acceptance criteria of the ticket you are considering,
   before you choose it.

Do not re-run the review that produced this backlog, re-import the backlog,
recreate existing tickets, or redo work already Done. A Done ticket is reopened
only when there is a specific, documented regression recorded against it (as
AI-092 records its remaining defect); absent that, treat Done as finished.

## Choosing work

- Select the highest-priority eligible Ready ticket whose dependencies are all
  Done. Priority is P1 over P2 over P3; among equal priority, prefer the ticket
  that unblocks the most others.
- Work on one ticket at a time, within this routine's existing scope and schedule.
  Do not combine tickets or start a second before the first is merged.
- If no ticket is eligible, say so and stop rather than inventing work.

After a ticket is completed or blocked, replenish a small Ready queue: promote the
highest-priority eligible Backlog items whose dependencies are Done, so the next
run has work waiting. A ticket blocked on one unavailable tool (for example AI-101
while Docker is unavailable) is marked Blocked with its reason and owner and never
stalls unrelated eligible work.

## Doing the work

- Follow the ticket's minimal change and satisfy its acceptance criteria; do not
  widen scope.
- Add or update meaningful regressions for the behaviour that changed. A bug fix
  carries the reproducing test that fails before it and passes after. Tests assert
  behaviour, not a helper's implementation.
- A change to a prompt, a rendering, or an output shape updates the matching
  prompt or output version identifier.
- Run the local checks before pushing: `ruff format --check .`, `ruff check .`,
  and `pytest`. Fix what they report.
- Verify CI through the authenticated GitHub tooling, on the actual commits: the
  pull request head, and, after merge, the `main` commit. A failed, cancelled or
  missing run is not success. Keep waits bounded; never poll unauthenticated
  endpoints or loop indefinitely.
- Mark a ticket Done only after its acceptance criteria are met and the merged
  result is verified green on `main`. Set the board status; add one concise Recent
  Progress entry.

## Boundaries

- Respect permissions. Changes under `.github/workflows/` and repository settings
  need the maintainer's access; when a ticket needs one, mark it Blocked, record
  the exact change and the responsible owner, and move to eligible work.
- Record every blocker with a clear next action and owner, in the ticket body and
  on the board.
- Avoid filler: no empty or timestamp-only commits, no splitting a trivial change
  to raise a count, no repetitive README progress narratives. One concise progress
  entry per landed ticket is enough.
- Keep changes focused: no unrelated refactoring in a feature or fix pull request.
