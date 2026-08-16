"""Declaring and reading tracked incidents.

The router validates the request; this module turns it into a store operation.
Declaring assigns the identifier and timestamps and starts the incident open,
then persists it; reading looks an incident up or assembles a page of them. The
lifecycle and the declaration rules live in the incident package, not here, so
this module only wires a validated request to the store.
"""

from datetime import datetime

from opsbrief.events import as_utc
from opsbrief.incidents import (
    Incident,
    IncidentDeclaration,
    IncidentPage,
    IncidentQuery,
)
from opsbrief.storage import IncidentStore


def declare_incident(
    store: IncidentStore, declaration: IncidentDeclaration, now: datetime
) -> Incident:
    """Declare an incident from ``declaration`` and store it.

    The incident is opened at ``now`` with a fresh identifier and the posted
    title, severity and events, then persisted. A clash on the generated
    identifier surfaces from the store rather than overwriting a tracked
    incident, exactly as it would for a direct store write.
    """
    incident = Incident.declare(
        title=declaration.title,
        severity=declaration.severity,
        event_ids=list(declaration.event_ids),
        at=as_utc(now),
    )
    return store.add(incident)


def get_incident(store: IncidentStore, incident_id: str) -> Incident | None:
    """Return the stored incident with ``incident_id``, or ``None`` if there is none.

    The caller decides how a missing incident is reported; the service only
    looks it up and never mutates the store.
    """
    return store.get(incident_id)


def list_incidents(store: IncidentStore, query: IncidentQuery) -> IncidentPage:
    """Return the page of stored incidents matching ``query``.

    The page carries the incidents themselves, most recently opened first,
    alongside the total number of matches across all pages, so a caller can tell
    whether more pages remain without fetching them. Reads never mutate the store.
    """
    incidents = store.list_incidents(
        status=query.status,
        limit=query.limit,
        offset=query.offset,
    )
    total = store.count(status=query.status)
    return IncidentPage(
        total=total,
        limit=query.limit,
        offset=query.offset,
        incidents=incidents,
    )
