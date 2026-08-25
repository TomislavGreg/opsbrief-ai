"""A worked quality-control incident example.

This builds on the sports-operations match-day fixture: it declares an incident
around the rejected goal-line technology calibration check and walks it through
the incident lifecycle at fixed match-day instants, then phrases the result with
a scripted fake provider, so the incident model, its transitions and an AI
incident summary can be shown over realistic match-operations material without a
database, a running server or a real model.

The example is deterministic. The incident carries a stable id, every lifecycle
instant is fixed, and the default provider returns
:data:`SAMPLE_QC_INCIDENT_SUMMARY` verbatim, so the same call always yields the
same incident and summary. The summary is illustrative phrasing of the kind a
duty manager would read; the status, severity, span, resolution note and cited
event underneath it are the real deterministic picture the service decides.
"""

from datetime import UTC, datetime

from opsbrief.ai import AIProvider, FakeAIProvider
from opsbrief.events import Event
from opsbrief.incidents import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentSummary,
    generate_incident_summary,
)
from opsbrief.samples import load_sample_match_stored_events

#: Stored id of the fixture event the incident is declared from: the rejected
#: goal-line technology calibration check at the Kop end. It is the ``external_id``
#: the match-day fixture carries for that event, which
#: :func:`load_sample_match_stored_events` uses as the stored id.
SAMPLE_QC_EVENT_ID = "match-qc-glt-2"

#: Stable identifier for the example incident, so the same call always yields an
#: incident with the same id and anything built on it stays reproducible.
SAMPLE_QC_INCIDENT_ID = "sample-qc-glt-2"

#: The instant the incident is declared: shortly after the calibration check is
#: rejected on the match day the fixture describes.
SAMPLE_QC_INCIDENT_DECLARED_AT = datetime(2026, 9, 12, 10, 30, tzinfo=UTC)

#: The instant the incident is picked up and actively worked.
SAMPLE_QC_INCIDENT_INVESTIGATING_AT = datetime(2026, 9, 12, 10, 45, tzinfo=UTC)

#: The instant the fix is in place and the system is watched for recurrence.
SAMPLE_QC_INCIDENT_MONITORING_AT = datetime(2026, 9, 12, 12, 10, tzinfo=UTC)

#: The instant the incident is resolved, before kickoff.
SAMPLE_QC_INCIDENT_RESOLVED_AT = datetime(2026, 9, 12, 12, 40, tzinfo=UTC)

#: The operator note recorded when the incident is resolved, explaining how the
#: rejected check was put right.
SAMPLE_QC_RESOLUTION_NOTE = (
    "Recalibrated the Kop-end goal-line camera array, re-ran the calibration check "
    "within tolerance and signed off with the match officials."
)

#: An illustrative one-line summary for the example incident, in a duty manager's
#: voice. It is returned verbatim by the default fake provider so the example
#: reads naturally and stays deterministic; the deterministic picture a reader
#: acts on (the status, severity, span, resolution note and cited event) comes
#: from the incident and its timeline, not this text.
SAMPLE_QC_INCIDENT_SUMMARY = (
    "The Kop-end goal-line technology calibration check was rejected for a camera "
    "alignment out of tolerance. It was investigated, the array was recalibrated and "
    "re-checked within tolerance, and the system was watched before being signed off "
    "with the match officials ahead of kickoff."
)


def build_sample_qc_incident(
    *,
    at_declared: datetime = SAMPLE_QC_INCIDENT_DECLARED_AT,
    at_investigating: datetime = SAMPLE_QC_INCIDENT_INVESTIGATING_AT,
    at_monitoring: datetime = SAMPLE_QC_INCIDENT_MONITORING_AT,
    at_resolved: datetime = SAMPLE_QC_INCIDENT_RESOLVED_AT,
) -> Incident:
    """Declare the QC incident and walk it through the lifecycle to resolved.

    The incident is declared from the rejected calibration check
    (:data:`SAMPLE_QC_EVENT_ID`) and moved through ``investigating`` and
    ``monitoring`` to ``resolved``, recording :data:`SAMPLE_QC_RESOLUTION_NOTE` as
    it is put right. The instants default to the fixed match-day moments above, so
    the returned incident is deterministic. Nothing is stored: the function returns
    the resolved incident and leaves the caller to persist it if they want to.
    """
    incident = Incident.declare(
        title="Goal-line technology calibration rejected at the Kop end",
        severity=IncidentSeverity.HIGH,
        event_ids=[SAMPLE_QC_EVENT_ID],
        at=at_declared,
        incident_id=SAMPLE_QC_INCIDENT_ID,
    )
    incident = incident.transition_to(IncidentStatus.INVESTIGATING, at=at_investigating)
    incident = incident.transition_to(IncidentStatus.MONITORING, at=at_monitoring)
    incident = incident.transition_to(
        IncidentStatus.RESOLVED, at=at_resolved, note=SAMPLE_QC_RESOLUTION_NOTE
    )
    return incident


def build_sample_qc_incident_summary(
    provider: AIProvider | None = None,
    *,
    incident: Incident | None = None,
    events: list[Event] | None = None,
) -> IncidentSummary:
    """Summarise the worked QC incident against the match-day fixture.

    The incident defaults to the resolved one :func:`build_sample_qc_incident`
    walks through the lifecycle, and the events to the match-day fixture loaded as
    stored events, so the cited calibration check resolves. When no provider is
    given a fake one scripted with :data:`SAMPLE_QC_INCIDENT_SUMMARY` is used, so
    the example is fully offline and reproducible; pass a provider to phrase the
    same deterministic picture differently. The status, severity, span, resolution
    note and cited event come from the incident and its timeline regardless of the
    provider, so the example always traces back to the fixture's event.
    """
    if incident is None:
        incident = build_sample_qc_incident()
    if events is None:
        events = load_sample_match_stored_events()
    if provider is None:
        provider = FakeAIProvider(responses=[SAMPLE_QC_INCIDENT_SUMMARY])
    return generate_incident_summary(incident, events, provider)


__all__ = [
    "SAMPLE_QC_EVENT_ID",
    "SAMPLE_QC_INCIDENT_DECLARED_AT",
    "SAMPLE_QC_INCIDENT_ID",
    "SAMPLE_QC_INCIDENT_INVESTIGATING_AT",
    "SAMPLE_QC_INCIDENT_MONITORING_AT",
    "SAMPLE_QC_INCIDENT_RESOLVED_AT",
    "SAMPLE_QC_INCIDENT_SUMMARY",
    "SAMPLE_QC_RESOLUTION_NOTE",
    "build_sample_qc_incident",
    "build_sample_qc_incident_summary",
]
