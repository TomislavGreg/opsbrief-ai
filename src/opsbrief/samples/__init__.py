"""Synthetic operational-event fixtures.

A small, coherent set of made-up operational events describing a single event
day at a venue: unfilled shifts, an overdue safety inspection, blocked work, a
ticketing integration failing repeatedly, a rejected quality check and a power
alert. They exist so demos, documentation examples and later phases (risk
detection and brief generation) have realistic material to work against without
anyone needing to hand-write payloads.

The data is entirely fictional. This is a public repository and the fixtures
carry no private, customer or personal data, in line with the project's data
policy.
"""

import json
from importlib.resources import files

from opsbrief.events import EventInput

#: Name of the packaged JSON file holding the sample event payloads.
SAMPLE_EVENTS_FILENAME = "events.json"


def load_sample_events() -> list[EventInput]:
    """Return the packaged sample events as validated :class:`EventInput` models.

    The payloads are read from the package's ``events.json`` and validated
    through the same contract producers submit against, so a fixture that drifts
    out of line with the schema fails loudly here rather than misleading a demo
    or a downstream test.
    """
    raw = files(__package__).joinpath(SAMPLE_EVENTS_FILENAME).read_text(encoding="utf-8")
    payloads = json.loads(raw)
    if not isinstance(payloads, list):
        raise ValueError("sample events file must contain a JSON array of events")
    return [EventInput(**payload) for payload in payloads]


__all__ = ["SAMPLE_EVENTS_FILENAME", "load_sample_events"]
