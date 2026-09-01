"""Laying a tracked incident's cited events out in time, against the stored events.

The router looks an incident up and hands this module the incident store and the
event store; it reads the tracked incident and the whole event history and
resolves the incident's cited events into a timeline, oldest first. No model
takes part: the timeline is a deterministic view of the incident and the events,
exactly as ``build_incident_timeline`` builds it. Reads never mutate either store.
"""

from opsbrief.incidents import IncidentTimeline, build_incident_timeline
from opsbrief.services.history import read_all_events
from opsbrief.storage import EventStore, IncidentStore


def report_incident_timeline(
    incident_store: IncidentStore,
    event_store: EventStore,
    incident_id: str,
) -> IncidentTimeline | None:
    """Return the timeline of the tracked incident with ``incident_id``.

    The incident is read from ``incident_store``; its cited events are resolved
    against the whole history in ``event_store`` and laid out oldest first.
    Returns ``None`` when no incident carries the identifier, so the caller can
    report a missing incident. A cited event that no stored event answers to is
    carried in the timeline's ``missing_event_ids`` rather than failing the
    request, so a gap in the evidence is stated plainly.
    """
    incident = incident_store.get(incident_id)
    if incident is None:
        return None
    events = read_all_events(event_store)
    return build_incident_timeline(incident, events)
