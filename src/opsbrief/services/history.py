"""Reading the whole stored event history for the services that need it.

Some services judge against every stored event rather than a single page: a
risk depends on all the evidence, and a daily brief is built from the full
picture. This is where that whole-history read lives once instead of in each
service.
"""

from opsbrief.events import Event
from opsbrief.storage import EventStore


def read_all_events(store: EventStore) -> list[Event]:
    """Return every stored event, so a caller judges against the full history.

    The store reads the whole history in one snapshot rather than gathering
    separate pages, because a whole-history read must not stop early (an overdue
    task from last week still matters) and must not stitch pages a concurrent
    write could shift: accumulating offset pages once let an event inserted
    between two page reads drop the new row and repeat the one on the boundary.
    Reading it in one query gives one coherent snapshot with no gaps or repeats.
    Reads never mutate the store.
    """
    return store.list_all_events()
