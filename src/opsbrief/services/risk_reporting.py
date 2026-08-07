"""Assembling the current risk picture from stored events.

The router hands this module the store and the instant to judge against; it
reads every stored event, runs the canonical rule set over them, ranks what the
rules raise and returns the snapshot the caller receives. Reads never mutate the
store, and no language model takes part: the snapshot is a deterministic function
of the events and the instant.
"""

from datetime import datetime

from opsbrief.events import Event, as_utc
from opsbrief.risks import RiskList, default_rules, detect_risks, prioritize
from opsbrief.storage import EventStore

#: How many events to read per page while gathering the whole history.
_PAGE = 500


def _all_events(store: EventStore) -> list[Event]:
    """Return every stored event, so a rule judges against the full history.

    Events are read a page at a time and gathered, rather than capped at one
    page, because a risk depends on all the evidence: an overdue task from last
    week still matters. The store's ordering is stable, so paging walks the whole
    history without gaps or repeats.
    """
    events: list[Event] = []
    offset = 0
    while True:
        page = store.list_events(limit=_PAGE, offset=offset)
        events.extend(page)
        if len(page) < _PAGE:
            return events
        offset += _PAGE


def list_risks(store: EventStore, now: datetime) -> RiskList:
    """Return the current risks across the stored events, most urgent first.

    Every implemented rule is run over the full event history at ``now``, and the
    risks they raise are ranked by priority. The snapshot records ``now`` as the
    instant it was taken, because risk is time-dependent, and every risk in it
    still cites the rule and events behind it.
    """
    reference = as_utc(now)
    risks = detect_risks(_all_events(store), default_rules(reference))
    return RiskList(generated_at=reference, risks=prioritize(risks))
