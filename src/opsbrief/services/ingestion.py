"""Accepting operational events from producing systems.

The router validates the submission; this module decides what becomes of it.
Recording an event means assigning it an identity and storing it, one at a time
or as a batch. A submission that carries an ``external_id`` already seen from
the same source is recognised as a resubmission rather than stored again.
"""

from opsbrief.events import Event, EventBatch, EventBatchResult, EventInput
from opsbrief.storage import EventStore


def record_event(store: EventStore, payload: EventInput) -> tuple[Event, bool]:
    """Store a submitted event, or recognise it as a resubmission.

    Returns the stored event and whether it was newly stored. A submission
    carrying an ``external_id`` the same source has already sent matches the
    event stored under that key: the previously stored event is returned and
    nothing new is stored, so an at-least-once producer that retries does not
    create a duplicate. A submission with no ``external_id`` is always stored.

    The stored form carries the service-assigned ``id`` that generated briefs,
    risks and incidents cite, and the ``received_at`` timestamp recording when
    the service first accepted it.
    """
    event = Event.from_input(payload)
    stored = store.add_or_get(event)
    return stored, stored.id == event.id


def record_events(store: EventStore, batch: EventBatch) -> EventBatchResult:
    """Store a validated batch of events atomically and return their stored forms.

    Each event is assigned its own identity. A submission carrying an
    ``external_id`` the same source has already sent, whether stored earlier or
    appearing earlier in this same batch, is recognised as a resubmission: the
    previously stored event is returned in its place and nothing new is stored
    for it, so an at-least-once producer that retries a batch does not create
    duplicates. The batch is stored all-or-nothing: if any identifier clashes
    with a stored event, none of the batch is kept.

    The result returns one event per submitted event, in order, and its
    ``count`` reports how many were newly stored; the remainder were recognised
    as resubmissions and can be told apart because their ``id`` predates the
    request.
    """
    events = [Event.from_input(payload) for payload in batch.events]
    resolved = store.add_all_or_get(events)
    stored = sum(1 for event, result in zip(events, resolved, strict=True) if result.id == event.id)
    return EventBatchResult(count=stored, events=resolved)
