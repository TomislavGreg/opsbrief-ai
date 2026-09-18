"""A deterministic offline narrative for an incident summary.

Like the daily brief, an incident summary runs offline by default with no model.
Rather than echo the prompt material or leave the summary empty, the service
composes a short narrative from the incident and its timeline.

The narrative is a pure function of the incident and the timeline: the same inputs
always yield the same sentence, and it can never contradict the picture it stands
beside, because it is built from it. It states what the incident is, where it sits
in its lifecycle, the span and size of its timeline (or that no cited event
resolves), and how it was resolved when a note records that. No model takes part,
which is what :data:`~opsbrief.verification.SummaryStatus.DETERMINISTIC` records.
"""

from collections.abc import Container

from opsbrief.exclusion import EXCLUSION_PLACEHOLDER, shown_free_text, shown_incident_title
from opsbrief.incidents.lifecycle import IncidentStatus
from opsbrief.incidents.schema import Incident
from opsbrief.incidents.timeline import IncidentTimeline


def _count(n: int, noun: str) -> str:
    """Return ``n`` with ``noun`` pluralised the plain English way."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def compose_incident_narrative(
    incident: Incident,
    timeline: IncidentTimeline,
    *,
    excluded_fields: Container[str] = frozenset(),
) -> str:
    """Compose a short, deterministic summary of ``incident`` and its ``timeline``.

    The sentence restates the deterministic picture: the incident's title, status
    and severity, its timeline span and size (or that no cited event resolves), and
    its resolution note once it is resolved. It is derived only from the incident
    and the timeline, so equal inputs yield equal text and it never disagrees with
    the picture it summarises. Fields named in ``excluded_fields`` are held back the
    same way they are held back from a model.
    """
    title = shown_incident_title(incident.title, excluded_fields)
    lead = f'Incident "{title}" is {incident.status.value} ({incident.severity.value}).'

    if timeline.started_at is None:
        return (
            f"{lead} No cited event resolves to a stored record, so there is no "
            "timeline to describe."
        )

    if "occurred_at" in excluded_fields:
        span = EXCLUSION_PLACEHOLDER
    else:
        span = f"{timeline.started_at.isoformat()} to {timeline.ended_at.isoformat()}"
    sentence = f"{lead} Its timeline runs {span} across {_count(len(timeline.entries), 'event')}."

    if timeline.missing_event_ids:
        sentence += (
            f" {_count(len(timeline.missing_event_ids), 'cited event')} no longer "
            "resolve to a stored record."
        )

    terminal = incident.status in {IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
    if terminal and incident.resolution_note is not None:
        sentence += f" Resolved: {shown_free_text(incident.resolution_note, excluded_fields)}"
    return sentence
