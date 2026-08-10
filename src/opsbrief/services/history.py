"""Reading the whole stored event history for the services that need it.

Some services judge against every stored event rather than a single page: a
risk depends on all the evidence, and a daily brief is built from the full
picture. Both read the history the same way — a page at a time until the store
runs out — so that walk lives here once instead of in each service.
"""

from opsbrief.events import Event
from opsbrief.storage import EventStore

#: How many events to read per page while gathering the whole history.
_PAGE = 500


def read_all_events(store: EventStore) -> list[Event]:
    """Return every stored event, so a caller judges against the full history.

    Events are read a page at a time and gathered, rather than capped at one
    page, because a whole-history read must not stop early: an overdue task from
    last week still matters. The store's ordering is stable, so paging walks the
    history without gaps or repeats. Reads never mutate the store.
    """
    events: list[Event] = []
    offset = 0
    while True:
        page = store.list_events(limit=_PAGE, offset=offset)
        events.extend(page)
        if len(page) < _PAGE:
            return events
        offset += _PAGE
