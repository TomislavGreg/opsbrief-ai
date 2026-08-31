"""Summarising a tracked incident against the stored events.

The router looks an incident up and hands this module the incident store, the
event store and the configured provider; it reads the tracked incident and the
whole event history, resolves the incident's cited events into a timeline, and
asks the provider to phrase it. The division of labour the incident-summary
generation enforces is kept intact here: the timeline, the span and the source
event IDs a reader acts on are built without a model, and the provider only
phrases them, its output treated as untrusted. Reads never mutate either store.
"""

from collections.abc import Container

from opsbrief.ai import AIProvider
from opsbrief.incidents import IncidentSummary, generate_incident_summary
from opsbrief.services.history import read_all_events
from opsbrief.storage import EventStore, IncidentStore


def report_incident_summary(
    incident_store: IncidentStore,
    event_store: EventStore,
    incident_id: str,
    provider: AIProvider,
    *,
    excluded_fields: Container[str] = frozenset(),
) -> IncidentSummary | None:
    """Return the summary of the tracked incident with ``incident_id``.

    The incident is read from ``incident_store``; its cited events are resolved
    against the whole history in ``event_store`` into a timeline, and ``provider``
    phrases that picture into a summary, which is constrained as untrusted output.
    Returns ``None`` when no incident carries the identifier, so the caller can
    report a missing incident. A cited event that no stored event answers to is
    carried in the summary's ``missing_event_ids`` rather than failing the request,
    so a gap in the evidence is stated plainly.

    Event fields named in ``excluded_fields`` are held back from the timeline the
    provider is shown, so a deployment can narrow the model's view without changing
    the incident's cited evidence or its span.
    """
    incident = incident_store.get(incident_id)
    if incident is None:
        return None
    events = read_all_events(event_store)
    return generate_incident_summary(incident, events, provider, excluded_fields=excluded_fields)
