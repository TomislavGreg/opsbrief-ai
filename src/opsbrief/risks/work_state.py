"""Projecting a work entity's current state from its event history.

The overdue and blocked rules describe operational work: a task, a shift, an
inspection. A producer reports that work over time as its state changes, keyed to
a stable entity. The integration contract says a later state change (a resolved
or cancelled event for the same entity) is how a situation is cleared, and that
the risk picture is recomputed from the current events every time it is read.

A work entity is identified by its producing ``source`` together with the
``entity_type`` and ``entity_id`` the producer attaches. Events carrying that
pair are grouped and ordered by occurrence, and the most recent one is the
entity's current state: it decides whether the work is still blocked or overdue,
or has since been resolved or cancelled. Events without an entity pair cannot be
correlated across reports, so each is treated on its own, exactly as it was before
work was grouped.

The history itself is never discarded. Grouping decides what the current risk is;
every event stays stored as evidence and keeps being retrievable.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from opsbrief.events import Event, EventStatus

#: A work entity's key: the producing source, the entity kind and its id.
WorkKey = tuple[str, str, str]

#: Statuses in which a piece of work is finished, so its current state raises no
#: blocked or overdue risk however its earlier events read.
TERMINAL_STATUSES = frozenset({EventStatus.RESOLVED, EventStatus.CANCELLED})


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


def _order_key(event: Event) -> tuple[object, object, str]:
    """Return the ordering key that puts an entity's events oldest first.

    Occurrence time decides the order, so the current state is what most recently
    happened rather than what was received last. Receipt time and then the id break
    ties, so events sharing an occurrence instant still order deterministically.
    """
    return (event.occurred_at, event.received_at, event.id)


@dataclass(frozen=True)
class WorkState:
    """The current state of one work entity, with the history behind it.

    ``events`` is the entity's whole history, oldest first, kept as evidence.
    ``current`` is the most recent of them and decides the state a rule acts on.
    """

    key: WorkKey
    events: tuple[Event, ...]

    @property
    def current(self) -> Event:
        """The most recent event, whose state is the entity's current state."""
        return self.events[-1]

    @property
    def is_cleared(self) -> bool:
        """Whether the work is finished: its current status is terminal."""
        return self.current.status in TERMINAL_STATUSES

    def blocked_run_start(self) -> Event | None:
        """Return the event that began the current unbroken run of blocked state.

        When the current status is blocked, this is the earliest event in the
        trailing run of consecutive blocked reports, so how long the work has been
        blocked measures from when it became blocked rather than from the latest
        re-report. It is the event that established the current blocked condition,
        the one a blocked risk cites. Returns ``None`` when the current status is
        not blocked.
        """
        if self.current.status is not EventStatus.BLOCKED:
            return None
        start = self.current
        for event in reversed(self.events[:-1]):
            if event.status is EventStatus.BLOCKED:
                start = event
            else:
                break
        return start


def group_work(events: Sequence[Event]) -> tuple[list[WorkState], list[Event]]:
    """Split events into current work states and independent unkeyed events.

    Events carrying an entity pair are grouped by :func:`work_key` and ordered
    oldest first into one :class:`WorkState` per entity; events without a pair are
    returned separately, in input order, for a rule to judge on their own. The work
    states come back ordered by key, so detection over them is stable.
    """
    keyed: dict[WorkKey, list[Event]] = {}
    unkeyed: list[Event] = []
    for event in events:
        key = work_key(event)
        if key is None:
            unkeyed.append(event)
        else:
            keyed.setdefault(key, []).append(event)
    states = [
        WorkState(key=key, events=tuple(sorted(group, key=_order_key)))
        for key, group in sorted(keyed.items())
    ]
    return states, unkeyed
