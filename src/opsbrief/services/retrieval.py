"""Reading stored operational events back out.

The router validates the query; this module turns it into a store lookup and
assembles the page the caller receives. Reads never mutate the store.
"""

from opsbrief.events import Event, EventPage, EventQuery
from opsbrief.storage import EventStore


def get_event(store: EventStore, event_id: str) -> Event | None:
    """Return the stored event with ``event_id``, or ``None`` if there is none.

    The caller decides how a missing event is reported; the service only looks
    it up and never mutates the store.
    """
    return store.get(event_id)


def list_events(store: EventStore, query: EventQuery) -> EventPage:
    """Return the page of stored events matching ``query``.

    The page carries the events themselves alongside the total number of matches
    across all pages, so a caller can tell whether more pages remain without
    fetching them. The rows and the total are read from one store snapshot, so
    within a request the total agrees with the page rather than counting a write
    that the page did not see.
    """
    events, total = store.list_page(
        source=query.source,
        event_type=query.event_type,
        severity=query.severity,
        status=query.status,
        entity_type=query.entity_type,
        entity_id=query.entity_id,
        occurred_from=query.occurred_from,
        occurred_to=query.occurred_to,
        limit=query.limit,
        offset=query.offset,
    )
    return EventPage(total=total, limit=query.limit, offset=query.offset, events=events)
