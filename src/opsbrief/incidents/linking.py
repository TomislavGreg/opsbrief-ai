"""Resolving an incident's cited events against stored event records.

An incident carries the identifiers of the events behind it, not the events
themselves, so that it stays a small, stable record. To act on an incident a
reader needs the events those identifiers point at. :func:`resolve_incident_events`
is that lookup: it turns the incident's ``event_ids`` into the stored
:class:`~opsbrief.events.schema.Event` records they name, in the order the
incident cites them, and reports any identifier that no longer resolves.

The resolution is a pure function of the incident and the events it is given —
no model, no store access of its own — so a caller decides which events to
resolve against and the result is deterministic.
"""

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict, Field

from opsbrief.events.schema import Event
from opsbrief.incidents.schema import Incident


class IncidentEvents(BaseModel):
    """An incident's cited events, resolved against stored event records.

    ``events`` are the resolved records in the order the incident cites them, so
    the evidence reads in the sequence it was linked. ``missing_event_ids`` names
    any identifier the incident cites that no stored event answered to, so a gap
    in the evidence is stated plainly rather than passed over — the two together
    account for every identifier on the incident.
    """

    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(
        description="Identifier of the incident whose events were resolved.",
    )
    events: list[Event] = Field(
        description="The resolved stored events, in the order the incident cites them.",
    )
    missing_event_ids: list[str] = Field(
        description="Cited identifiers that no stored event answered to, in cited order.",
    )


def resolve_incident_events(incident: Incident, events: Iterable[Event]) -> IncidentEvents:
    """Resolve ``incident``'s cited events against ``events``.

    ``events`` is any collection of stored events to look the incident's
    identifiers up in — typically the current event history. Each identifier the
    incident cites is matched to a stored event by ``id``; matches are returned in
    the incident's cited order, and any identifier with no match is reported as
    missing. An event present in ``events`` but not cited by the incident is
    ignored, so the result covers exactly the incident's evidence and nothing else.
    """
    by_id = {event.id: event for event in events}
    resolved: list[Event] = []
    missing: list[str] = []
    for event_id in incident.event_ids:
        event = by_id.get(event_id)
        if event is None:
            missing.append(event_id)
        else:
            resolved.append(event)
    return IncidentEvents(
        incident_id=incident.id,
        events=resolved,
        missing_event_ids=missing,
    )
