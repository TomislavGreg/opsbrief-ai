"""Synthetic operational-event fixtures.

Two small, coherent sets of made-up operational events, both describing a single
day of activity:

- A general venue event day (``events.json``): unfilled shifts, an overdue
  safety inspection, blocked work, a ticketing integration failing repeatedly, a
  rejected quality check and a power alert.
- A sports-operations match day (``match_events.json``): short stewarding and an
  unfilled medic post, an overdue pitch inspection, a blocked scoreboard
  calibration, a broadcast feed failing repeatedly, a rejected goal-line
  technology check and a crowd-density alert. It gives Game Center readiness work
  realistic match-operations material.

They exist so demos, documentation examples and later phases (risk detection and
brief generation) have realistic material to work against without anyone needing
to hand-write payloads.

The data is entirely fictional. This is a public repository and the fixtures
carry no private, customer or personal data, in line with the project's data
policy.
"""

import json
from importlib.resources import files

from opsbrief.events import Event, EventInput

#: Name of the packaged JSON file holding the general venue sample events.
SAMPLE_EVENTS_FILENAME = "events.json"

#: Name of the packaged JSON file holding the sports-operations match-day events.
SAMPLE_MATCH_EVENTS_FILENAME = "match_events.json"


def _load_events(filename: str) -> list[EventInput]:
    """Return a packaged fixture file as validated :class:`EventInput` models.

    The payloads are read from ``filename`` in this package and validated through
    the same contract producers submit against, so a fixture that drifts out of
    line with the schema fails loudly here rather than misleading a demo or a
    downstream test.
    """
    raw = files(__package__).joinpath(filename).read_text(encoding="utf-8")
    payloads = json.loads(raw)
    if not isinstance(payloads, list):
        raise ValueError(f"sample events file {filename!r} must contain a JSON array of events")
    return [EventInput(**payload) for payload in payloads]


def load_sample_events() -> list[EventInput]:
    """Return the general venue sample events as validated :class:`EventInput` models."""
    return _load_events(SAMPLE_EVENTS_FILENAME)


def load_sample_match_events() -> list[EventInput]:
    """Return the sports-operations match-day sample events as validated models.

    These describe one football match day and are shaped so the deterministic
    risk rules recognise them: the pitch inspection is overdue, the scoreboard
    task is blocked, and the broadcast feed fails repeatedly without recovering.
    """
    return _load_events(SAMPLE_MATCH_EVENTS_FILENAME)


def _to_stored_event(payload: EventInput) -> Event:
    """Turn a sample submission into a stored event with a stable identifier.

    A brief, risk set or timeline traces back to the stored ``id`` of each event,
    so an example is only reproducible if those ids are stable. The fixtures carry
    an ``external_id`` per event, so using it as the stored ``id`` makes the same
    fixture always yield the same source event ids, without a store assigning a
    random one. ``received_at`` is pinned to the occurrence instant for the same
    reason. A fixture event with no ``external_id`` cannot be given a stable id, so
    it is refused rather than silently given a random one.
    """
    if payload.external_id is None:
        raise ValueError(
            f"sample event {payload.subject!r} has no external_id to use as a stable id"
        )
    return Event.from_input(payload, received_at=payload.occurred_at).model_copy(
        update={"id": payload.external_id}
    )


def load_sample_match_stored_events() -> list[Event]:
    """Return the match-day fixture as stored events with stable identifiers.

    The events are the same ones :func:`load_sample_match_events` validates, turned
    into stored :class:`~opsbrief.events.Event` records ready to feed the risk
    rules, a brief context or an incident timeline. Each event's ``external_id``
    becomes its stored ``id``, so the same fixture always resolves to the same
    source event ids and a demo built on it is reproducible.
    """
    return [_to_stored_event(payload) for payload in load_sample_match_events()]


# Imported after the loaders it depends on are defined, so the package can
# re-export the worked brief example without a circular import.
from opsbrief.samples.match_brief import (  # noqa: E402
    SAMPLE_MATCH_BRIEF_AT,
    SAMPLE_MATCH_BRIEF_SUMMARY,
    build_sample_match_brief,
)

__all__ = [
    "SAMPLE_EVENTS_FILENAME",
    "SAMPLE_MATCH_BRIEF_AT",
    "SAMPLE_MATCH_BRIEF_SUMMARY",
    "SAMPLE_MATCH_EVENTS_FILENAME",
    "build_sample_match_brief",
    "load_sample_events",
    "load_sample_match_events",
    "load_sample_match_stored_events",
]
