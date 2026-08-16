"""Declaring incidents from the risks recognised over stored events.

A risk already does the hard part of grouping related events: a deterministic
rule reads the stored events and cites the ones behind a concern. Declaring an
incident from a risk carries that grouping forward into a stateful record worth
tracking, without a language model and without re-deciding what belongs
together. The risk's cited events become the incident's evidence, its title
becomes the incident's title and its severity becomes the incident's severity,
so the incident traces back to exactly the events the rule fired on.

The declaration is a pure function of the risk and the instant it is declared
at, so the same risk always yields the same incident. Persisting it is a
separate step, left to the caller.
"""

from datetime import datetime

from opsbrief.incidents.schema import Incident, IncidentSeverity
from opsbrief.risks.schema import Risk, RiskSeverity

#: How a risk's severity maps onto an incident's. Both scales run ``low`` to
#: ``critical`` with no ``info`` level, so the mapping is one to one; it is
#: written out rather than inferred from the shared values so a change to either
#: scale is a deliberate edit here rather than a silent mismatch.
RISK_TO_INCIDENT_SEVERITY: dict[RiskSeverity, IncidentSeverity] = {
    RiskSeverity.LOW: IncidentSeverity.LOW,
    RiskSeverity.MEDIUM: IncidentSeverity.MEDIUM,
    RiskSeverity.HIGH: IncidentSeverity.HIGH,
    RiskSeverity.CRITICAL: IncidentSeverity.CRITICAL,
}


def declare_incident_from_risk(
    risk: Risk,
    *,
    at: datetime | None = None,
    incident_id: str | None = None,
) -> Incident:
    """Open an incident from ``risk`` and the events behind it.

    The new incident starts ``open`` and carries the risk's title, its mapped
    severity and its cited events in the order the risk cites them, so the
    incident traces back to the same evidence the risk does. ``at`` sets the
    opening instant, defaulting to now, and ``incident_id`` sets the identifier,
    defaulting to a fresh one. The risk itself is not stored on the incident: an
    incident is a stateful record, and the risk that seeded it is recomputed from
    the events rather than frozen.
    """
    return Incident.declare(
        title=risk.title,
        severity=RISK_TO_INCIDENT_SEVERITY[risk.severity],
        event_ids=list(risk.event_ids),
        at=at,
        incident_id=incident_id,
    )
