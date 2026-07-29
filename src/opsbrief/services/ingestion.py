"""Accepting operational events from producing systems.

The router validates the submission; this module decides what becomes of it.
Batch submission and duplicate protection are separate tickets, so for now
recording an event means assigning it an identity and storing it.
"""

from opsbrief.events import Event, EventInput
from opsbrief.storage import EventStore


def record_event(store: EventStore, payload: EventInput) -> Event:
    """Store a submitted event and return its stored form.

    The stored form carries the service-assigned ``id`` that generated briefs,
    risks and incidents cite, and the ``received_at`` timestamp recording when
    the service accepted it.
    """
    return store.add(Event.from_input(payload))
