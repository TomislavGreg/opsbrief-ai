"""Declaring incidents from the risks recognised over stored events.

A risk already does the hard part of grouping related events: a deterministic
rule reads the stored events and cites the ones behind a concern. Declaring an
incident from a risk carries that grouping forward into a stateful record worth
tracking, without a language model and without re-deciding what belongs
together. The risk's cited events become the incident's evidence, its title
becomes the incident's title and its severity becomes the incident's severity,
so the incident traces back to exactly the events the rule fired on.

The declaration is a pure function of the risks and the instant they are
declared at, so the same events always yield the same incidents. Persisting them
is a separate step: :func:`declare_incidents_from_events` returns the incidents
it opens and leaves the caller to store whichever it wants to track.
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from opsbrief.events.schema import Event
from opsbrief.incidents.schema import Incident, IncidentSeverity
from opsbrief.risks.engine import RiskRule, detect_risks
from opsbrief.risks.priority import prioritize
from opsbrief.risks.rules import default_rules
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


def declare_incidents_from_events(
    events: Iterable[Event],
    *,
    at: datetime | None = None,
    rules: Sequence[RiskRule] | None = None,
) -> list[Incident]:
    """Open an incident for every risk recognised over ``events``.

    The risks are detected with ``rules`` (the canonical rule set by default),
    judged against ``at`` (now by default) so the reference instant is shared by
    the detection and the incidents it seeds, and ranked most urgent first before
    an incident is declared for each. The result is therefore ordered most urgent
    first too, and events raising no risk produce no incident. Nothing is stored:
    the caller decides which of the returned incidents to persist and track.
    """
    reference = at or datetime.now(UTC)
    rule_set = default_rules(reference) if rules is None else rules
    risks = prioritize(detect_risks(events, rule_set))
    return [declare_incident_from_risk(risk, at=reference) for risk in risks]
