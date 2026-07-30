"""Accepting operational events from producing systems.

The router validates the submission; this module decides what becomes of it.
Recording an event means assigning it an identity and storing it, one at a time
or as a batch. Duplicate protection by ``external_id`` is a separate ticket.
"""

from opsbrief.events import Event, EventBatch, EventBatchResult, EventInput
from opsbrief.storage import EventStore


def record_event(store: EventStore, payload: EventInput) -> Event:
    """Store a submitted event and return its stored form.

    The stored form carries the service-assigned ``id`` that generated briefs,
    risks and incidents cite, and the ``received_at`` timestamp recording when
    the service accepted it.
    """
    return store.add(Event.from_input(payload))


def record_events(store: EventStore, batch: EventBatch) -> EventBatchResult:
    """Store a validated batch of events atomically and return their stored forms.

    Each event is assigned its own identity. The batch is stored all-or-nothing:
    if any identifier clashes with a stored event, none of the batch is kept.
    """
    events = [Event.from_input(payload) for payload in batch.events]
    stored = store.add_all(events)
    return EventBatchResult(count=len(stored), events=stored)
