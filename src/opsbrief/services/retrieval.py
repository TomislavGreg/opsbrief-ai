"""Reading stored operational events back out.

The router validates the query; this module turns it into a store lookup and
assembles the page the caller receives. Reads never mutate the store.
"""

from opsbrief.events import EventPage, EventQuery
from opsbrief.storage import EventStore


def list_events(store: EventStore, query: EventQuery) -> EventPage:
    """Return the page of stored events matching ``query``.

    The page carries the events themselves alongside the total number of matches
    across all pages, so a caller can tell whether more pages remain without
    fetching them.
    """
    events = store.list_events(
        source=query.source,
        event_type=query.event_type,
        severity=query.severity,
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )
    total = store.count(
        source=query.source,
        event_type=query.event_type,
        severity=query.severity,
        status=query.status,
    )
    return EventPage(total=total, limit=query.limit, offset=query.offset, events=events)
