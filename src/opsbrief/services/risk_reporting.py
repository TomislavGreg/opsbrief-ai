"""Assembling the current risk picture from stored events.

The router hands this module the store and the instant to judge against; it
reads every stored event, runs the canonical rule set over them, ranks what the
rules raise and returns the snapshot the caller receives. Reads never mutate the
store, and no language model takes part: the snapshot is a deterministic function
of the events and the instant.
"""

from datetime import datetime

from opsbrief.events import as_utc
from opsbrief.risks import RiskList, default_rules, detect_risks, prioritize
from opsbrief.services.history import read_all_events
from opsbrief.storage import EventStore


def list_risks(store: EventStore, now: datetime) -> RiskList:
    """Return the current risks across the stored events, most urgent first.

    Every implemented rule is run over the full event history at ``now``, and the
    risks they raise are ranked by priority. The snapshot records ``now`` as the
    instant it was taken, because risk is time-dependent, and every risk in it
    still cites the rule and events behind it.
    """
    reference = as_utc(now)
    risks = detect_risks(read_all_events(store), default_rules(reference))
    return RiskList(generated_at=reference, risks=prioritize(risks))
