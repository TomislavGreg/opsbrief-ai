"""Resolving cited event identifiers into descriptive source references.

Every generated output, a daily brief and an incident summary alike, traces back
to the source events behind it through a list of event identifiers. An identifier
tells a reader which event to look up, not what it was. A source reference closes
that gap: it resolves an identifier against the stored events into a compact
descriptor, so the generated output is self-describing. A reader sees what each
cited event was without a second lookup, and a cited identifier that no stored
event answers to is marked unresolved rather than passed over.

Resolution is deterministic and holds no model involvement, exactly like the
evidence it describes: the same identifiers and events always yield the same
references. It carries the fields a brief or a timeline describes an event with,
not the free-form ``metadata``, so a reference stays as bounded as the digests it
sits alongside.
"""

from collections.abc import Iterable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opsbrief.events import Event, EventSeverity, EventStatus


class SourceReference(BaseModel):
    """A cited event identifier resolved to what the event was.

    A reference always names the ``event_id`` it was built for and whether a
    stored event ``resolved`` it. When one did, the descriptive fields carry the
    event's ``source``, ``event_type``, ``subject``, ``occurred_at``, ``severity``
    and ``status``, the same fields a brief digest or a timeline entry describes an
    event with; the free-form ``metadata`` is left out on purpose, keeping a
    reference bounded and producer-supplied detail out of it. When no stored event
    answered to the identifier the descriptive fields are all null, so a gap in the
    evidence is stated plainly rather than implied away.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the cited event the reference was built for.",
    )
    resolved: bool = Field(
        description="Whether a stored event answered to the identifier.",
    )
    source: str | None = Field(
        default=None,
        description="System that produced the event, or null when unresolved.",
    )
    event_type: str | None = Field(
        default=None,
        description="Lowercase dotted name describing what happened, or null when unresolved.",
    )
    subject: str | None = Field(
        default=None,
        description="One-line human-readable description, or null when unresolved.",
    )
    occurred_at: datetime | None = Field(
        default=None,
        description="When the event happened, in UTC, or null when unresolved.",
    )
    severity: EventSeverity | None = Field(
        default=None,
        description="Producer-stated severity of the event, or null when unresolved.",
    )
    status: EventStatus | None = Field(
        default=None,
        description="State the event describes, when known, or null when unresolved.",
    )

    @classmethod
    def from_event(cls, event: Event) -> "SourceReference":
        """Build a resolved reference describing ``event``."""
        return cls(
            event_id=event.id,
            resolved=True,
            source=event.source,
            event_type=event.event_type,
            subject=event.subject,
            occurred_at=event.occurred_at,
            severity=event.severity,
            status=event.status,
        )

    @classmethod
    def unresolved(cls, event_id: str) -> "SourceReference":
        """Build a reference for a cited ``event_id`` no stored event answered to."""
        return cls(event_id=event_id, resolved=False)


def build_source_references(
    event_ids: Sequence[str],
    events: Iterable[Event],
) -> list[SourceReference]:
    """Resolve ``event_ids`` against ``events`` into references, in the given order.

    Each identifier becomes one reference in the order it is given, so the result
    lines up one to one with the ``source_event_ids`` a generated output already
    carries. An identifier a stored event answers to resolves to that event's
    descriptor; one that none answers to becomes an unresolved reference rather
    than being dropped, so every cited identifier is accounted for exactly once. A
    repeated identifier yields a reference each time it appears, so the caller
    decides whether to deduplicate before resolving. ``events`` is not mutated.
    """
    by_id: dict[str, Event] = {event.id: event for event in events}
    references: list[SourceReference] = []
    for event_id in event_ids:
        event = by_id.get(event_id)
        if event is None:
            references.append(SourceReference.unresolved(event_id))
        else:
            references.append(SourceReference.from_event(event))
    return references
