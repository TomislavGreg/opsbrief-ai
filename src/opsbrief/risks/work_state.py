"""Projecting a work entity's current state from its event history.

The overdue and blocked rules describe operational work: a task, a shift, an
inspection. A producer reports that work over time as its state changes, keyed to
a stable entity. The integration contract says a later state change (a resolved
or cancelled event for the same entity) is how a situation is cleared, and that
the risk picture is recomputed from the current events every time it is read.

A work entity is identified by its producing ``source`` together with the
``entity_type`` and ``entity_id`` the producer attaches. Events carrying that
pair are grouped, ordered by occurrence, and folded into one projected current
state.

The projection treats a later report as an update, not a replacement. Each event
carries only the fields the producer chose to state, so an omitted field leaves
the prior value standing:

- An event that states neither a ``status`` nor a ``due_at`` is informational (a
  progress comment, say). It carries no work state and is transparent: it leaves
  the known status, the known deadline and a continuous blocked run untouched,
  rather than erasing them by being the latest event.
- An event that states a ``status`` sets the current status. An event that states
  a ``due_at`` replaces the deadline. A non-terminal update that omits ``due_at``
  keeps the prior deadline (it simply did not mention it).
- Reaching a terminal status (resolved or cancelled) ends the work and clears its
  deadline, so a later reopen without a fresh ``due_at`` has no active deadline.
  That is the one explicit deadline removal, as against a merely omitted one.

How long work has been blocked is measured from the start of the current unbroken
run of blocked state, so re-affirming a block, or an informational comment during
one, does not reset the clock.

Events without an entity pair cannot be correlated across reports, so each is
treated on its own, exactly as it was before work was grouped. The history itself
is never discarded: grouping decides what the current risk is; every event stays
stored as evidence and keeps being retrievable.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from opsbrief.events import Event, EventStatus, as_utc

#: A work entity's key: the producing source, the entity kind and its id.
WorkKey = tuple[str, str, str]

#: Statuses in which a piece of work is finished, so its current state raises no
#: blocked or overdue risk however its earlier events read.
TERMINAL_STATUSES = frozenset({EventStatus.RESOLVED, EventStatus.CANCELLED})


def occurred_by(events: Sequence[Event], reference: datetime) -> list[Event]:
    """Return the events that had occurred by ``reference``, in input order.

    The risk picture is judged as of a single reference instant. An event whose
    ``occurred_at`` is after that instant describes something that has not yet
    happened as of the reference, so it is not part of the present picture: it can
    neither raise nor clear a current risk, nor count as recent activity. Applying
    this one boundary before every rule and the recent-events view keeps a future
    report (a scheduled resolution, a deadline set ahead of time) from reaching
    back into today's snapshot; advancing the reference past such an event admits
    it like any other.

    The boundary is on occurrence time, not receipt time, matching how every rule
    reasons about ``now`` (deadlines, blocked runs and failure windows are all read
    from ``occurred_at``). Receipt time only breaks ordering ties. ``reference`` is
    read in UTC to match the UTC ``occurred_at`` on stored events.
    """
    boundary = as_utc(reference)
    return [event for event in events if event.occurred_at <= boundary]


def work_key(event: Event) -> WorkKey | None:
    """Return the entity key an event is about, or ``None`` when it has none.

    The key is the producing ``source`` with the ``entity_type`` and ``entity_id``
    the producer attached. An event that names no entity pair cannot be correlated
    with another report and returns ``None``; the caller treats it independently.
    Two producers using the same id stay separate, because the source is part of
    the key.
    """
    if event.entity_type is not None and event.entity_id is not None:
        return (event.source, event.entity_type, event.entity_id)
    return None


def is_informational(event: Event) -> bool:
    """Return whether ``event`` carries no work state a rule reads.

    An informational event states neither a ``status`` nor a ``due_at``, so it
    changes nothing the overdue or blocked rules judge on. It is a notification
    (a progress note), not a state change, and must leave the entity's known
    state and continuous blocked duration unchanged rather than replacing them.
    """
    return event.status is None and event.due_at is None


def _order_key(event: Event) -> tuple[object, object, str]:
    """Return the ordering key that puts an entity's events oldest first.

    Occurrence time decides the order, so the current state is what most recently
    happened rather than what was received last. Receipt time and then the id break
    ties, so events sharing an occurrence instant still order deterministically.
    """
    return (event.occurred_at, event.received_at, event.id)


@dataclass(frozen=True)
class WorkState:
    """The projected current state of one work entity, and the history behind it.

    ``events`` is the entity's whole history, oldest first, kept as evidence. The
    remaining fields are the projection folded from that history: the current
    ``status`` and the event that set it, the current ``due_at`` deadline and the
    event that set it, and ``blocked_since``, the event that began the current
    unbroken run of blocked state. Each source event is a real stored event, so a
    risk built from the projection still traces to the event that established the
    condition it reports.
    """

    key: WorkKey
    events: tuple[Event, ...]
    status: EventStatus | None
    status_event: Event | None
    due_at: datetime | None
    due_event: Event | None
    blocked_since: Event | None

    @property
    def is_cleared(self) -> bool:
        """Whether the work is finished: its current status is terminal."""
        return self.status in TERMINAL_STATUSES

    def overdue_deadline(self, now: datetime) -> Event | None:
        """Return the event carrying the deadline if the work is overdue at ``now``.

        The work is overdue when its projected deadline has passed and its current
        status is not terminal. The event returned is the one that set the current
        deadline, so an overdue risk cites the report that established it. Returns
        ``None`` when there is no active deadline, the work is finished, or the
        deadline has not yet passed.
        """
        if self.due_at is None or self.due_event is None:
            return None
        if self.status in TERMINAL_STATUSES:
            return None
        return self.due_event if self.due_at < now else None


def _project(key: WorkKey, ordered: list[Event]) -> WorkState:
    """Fold an entity's ordered history into its projected current state.

    ``ordered`` is the entity's events oldest first. Informational events are
    transparent; a stated status or deadline updates the running projection; a
    terminal status clears the deadline. The blocked run is the trailing stretch
    of events whose effective status is blocked, so its start dates a continuous
    block rather than the latest re-report.
    """
    status: EventStatus | None = None
    status_event: Event | None = None
    due_at: datetime | None = None
    due_event: Event | None = None
    #: Each event paired with the status in effect once it is applied, so the
    #: blocked run can be traced back through transparent informational events.
    effective: list[tuple[Event, EventStatus | None]] = []

    for event in ordered:
        if not is_informational(event):
            if event.status is not None:
                status = event.status
                status_event = event
                if status in TERMINAL_STATUSES:
                    due_at = None
                    due_event = None
            if event.due_at is not None:
                due_at = event.due_at
                due_event = event
        effective.append((event, status))

    blocked_since = _blocked_run_start(effective) if status is EventStatus.BLOCKED else None
    return WorkState(
        key=key,
        events=tuple(ordered),
        status=status,
        status_event=status_event,
        due_at=due_at,
        due_event=due_event,
        blocked_since=blocked_since,
    )


def _blocked_run_start(effective: list[tuple[Event, EventStatus | None]]) -> Event | None:
    """Return the event that began the current unbroken run of blocked state.

    ``effective`` pairs each event with the status in effect after it is applied.
    The current run is the trailing stretch whose effective status is blocked; its
    first event is the report that set that block, since only a stated blocked
    status turns the effective status blocked. Informational comments inside the
    run inherit the block, so they neither break it nor become its start.
    """
    start: Event | None = None
    for event, status in reversed(effective):
        if status is EventStatus.BLOCKED:
            start = event
        else:
            break
    return start


def group_work(events: Sequence[Event]) -> tuple[list[WorkState], list[Event]]:
    """Split events into current work states and independent unkeyed events.

    Events carrying an entity pair are grouped by :func:`work_key`, ordered oldest
    first and folded into one :class:`WorkState` per entity; events without a pair
    are returned separately, in input order, for a rule to judge on their own. The
    work states come back ordered by key, so detection over them is stable.
    """
    keyed: dict[WorkKey, list[Event]] = {}
    unkeyed: list[Event] = []
    for event in events:
        key = work_key(event)
        if key is None:
            unkeyed.append(event)
        else:
            keyed.setdefault(key, []).append(event)
    states = [_project(key, sorted(group, key=_order_key)) for key, group in sorted(keyed.items())]
    return states, unkeyed
