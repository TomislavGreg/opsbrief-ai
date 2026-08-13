"""Assembling an incident's timeline from stored events.

An incident cites its events in the order they were linked, which is not
necessarily the order they happened. To read a disruption as a story, a duty
manager needs its events laid out in time: what happened first, what followed,
and when it ran from and to. :func:`build_incident_timeline` is that view. It
takes the events the incident cites, resolves them against the stored records,
and orders the resolved ones by when they occurred, oldest first.

The timeline is a pure function of the incident and the events it is given: no
model takes part, and the same inputs always yield the same timeline. It builds
on :func:`~opsbrief.incidents.linking.resolve_incident_events`, so a cited
identifier with no stored record is reported as missing here exactly as it is
there, and every cited identifier is accounted for once, as either an entry or a
missing id.
"""

from collections.abc import Iterable
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from opsbrief.events import Event, EventSeverity, EventStatus
from opsbrief.incidents.linking import resolve_incident_events
from opsbrief.incidents.schema import Incident


class TimelineEntry(BaseModel):
    """A stored event reduced to what an incident timeline shows.

    Like the digest a brief carries, an entry is smaller than the stored event:
    it keeps the fields a timeline describes an event with, and its ``id`` so a
    reader can look it up, but not the free-form ``metadata``. Metadata is left
    out on purpose, keeping the timeline bounded and producer-supplied detail out
    of any later model prompt until the redaction work of a later phase governs
    what may be shown.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the stored event, so the timeline can cite it.",
    )
    source: str = Field(
        min_length=1,
        max_length=64,
        description="System that produced the event, for example 'integrations'.",
    )
    event_type: str = Field(
        min_length=1,
        max_length=64,
        description="Lowercase dotted name describing what happened.",
    )
    subject: str = Field(
        min_length=1,
        max_length=200,
        description="One-line human-readable description of the event.",
    )
    occurred_at: datetime = Field(
        description="When the event happened, in UTC.",
    )
    severity: EventSeverity = Field(
        description="Producer-stated severity of the event.",
    )
    status: EventStatus | None = Field(
        default=None,
        description="State of the work or system the event describes, when known.",
    )

    @classmethod
    def from_event(cls, event: Event) -> "TimelineEntry":
        """Reduce a stored event to the entry a timeline shows it as."""
        return cls(
            id=event.id,
            source=event.source,
            event_type=event.event_type,
            subject=event.subject,
            occurred_at=event.occurred_at,
            severity=event.severity,
            status=event.status,
        )


class IncidentTimeline(BaseModel):
    """An incident's cited events laid out in the order they occurred.

    ``entries`` are the resolved events oldest first, so the timeline reads
    forward through the disruption; ties on ``occurred_at`` are broken by event
    id, so the order is total and independent of the order the events arrived in.
    ``missing_event_ids`` names any cited identifier no stored event answered to,
    in the incident's cited order, so a gap in the evidence is stated plainly.
    Together the two account for every identifier the incident cites.
    """

    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(
        description="Identifier of the incident the timeline was built for.",
    )
    entries: list[TimelineEntry] = Field(
        description="The resolved events, oldest first, ties broken by event id.",
    )
    missing_event_ids: list[str] = Field(
        description="Cited identifiers that no stored event answered to, in cited order.",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="When the first timeline event occurred, or null when there are none.",
    )
    @property
    def started_at(self) -> datetime | None:
        """Return when the earliest resolved event occurred, or ``None``.

        It is the span's start, derived from ``entries`` rather than stored, so
        it can never disagree with them. A timeline with no resolved events has
        no span, so this is ``None``.
        """
        return self.entries[0].occurred_at if self.entries else None

    @computed_field(  # type: ignore[prop-decorator]
        description="When the last timeline event occurred, or null when there are none.",
    )
    @property
    def ended_at(self) -> datetime | None:
        """Return when the latest resolved event occurred, or ``None``.

        It is the span's end, derived from ``entries`` rather than stored. For a
        single-event timeline it equals :attr:`started_at`; with no resolved
        events it is ``None``.
        """
        return self.entries[-1].occurred_at if self.entries else None


def build_incident_timeline(incident: Incident, events: Iterable[Event]) -> IncidentTimeline:
    """Assemble ``incident``'s timeline against ``events``.

    ``events`` is any collection of stored events to resolve the incident's cited
    identifiers in, typically the current event history. The cited events are
    resolved through :func:`resolve_incident_events`, so an identifier with no
    stored record is reported as missing rather than dropped, then ordered by when
    they occurred, oldest first, ties broken by event id. The incident is not
    mutated, and the same inputs always yield the same timeline.
    """
    resolved = resolve_incident_events(incident, events)
    ordered = sorted(resolved.events, key=lambda event: (event.occurred_at, event.id))
    return IncidentTimeline(
        incident_id=incident.id,
        entries=[TimelineEntry.from_event(event) for event in ordered],
        missing_event_ids=resolved.missing_event_ids,
    )
