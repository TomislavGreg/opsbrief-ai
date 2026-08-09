"""Assembling the daily-brief context from stored events.

This is the deterministic step behind a daily brief: given the stored events and
the instant to judge against, it runs the canonical risk rules, gathers a
bounded view of recent activity, and records where the picture is incomplete.
The result is a :class:`~opsbrief.brief.schema.BriefContext` a provider later
turns into prose. No language model takes part here — the context is a pure
function of the events and the instant, so the same inputs always produce the
same context.
"""

from collections.abc import Sequence
from datetime import datetime

from opsbrief.brief.schema import BriefContext, EventDigest
from opsbrief.events import Event, as_utc
from opsbrief.risks import Risk, default_rules, detect_risks, prioritize

#: How many recent events a brief context carries by default. The view is bounded
#: so the eventual prompt stays small no matter how much history the store holds.
DEFAULT_RECENT_EVENTS = 20


def _digest(event: Event) -> EventDigest:
    """Reduce a stored event to the digest a brief describes and cites it with."""
    return EventDigest(
        id=event.id,
        source=event.source,
        event_type=event.event_type,
        subject=event.subject,
        occurred_at=event.occurred_at,
        severity=event.severity,
        status=event.status,
    )


def _order_newest_first(events: Sequence[Event]) -> list[Event]:
    """Return the events most recently occurred first, ties broken by id.

    The ordering is total and independent of the order the events arrived in, so
    the recent-events view a context carries is deterministic.
    """
    by_id = sorted(events, key=lambda event: event.id)
    return sorted(by_id, key=lambda event: event.occurred_at, reverse=True)


def _notes(event_count: int, risks: Sequence[Risk], shown: int) -> list[str]:
    """Describe where the picture is incomplete, so a brief can say so plainly.

    Each note is a deterministic statement of fact about the material, not a
    judgement: no events to draw on, no risks found, or a recent-events view that
    omits older events because it is bounded.
    """
    if event_count == 0:
        return ["No operational events have been recorded, so the brief has no source data."]
    notes: list[str] = []
    if not risks:
        notes.append(f"No risks were detected across the {event_count} events considered.")
    if shown < event_count:
        notes.append(
            f"Showing the {shown} most recent of {event_count} events; "
            "older events are omitted from the brief context."
        )
    return notes


def build_brief_context(
    events: Sequence[Event],
    now: datetime,
    *,
    max_recent_events: int = DEFAULT_RECENT_EVENTS,
) -> BriefContext:
    """Assemble the material a daily brief for ``now`` is built from.

    The canonical risk rules run over the whole of ``events`` at ``now``, so a
    risk is judged against the full history rather than the bounded recent view,
    and the risks are ranked most urgent first. The recent-events view is capped
    at ``max_recent_events`` so the context — and any prompt built from it — stays
    bounded. ``events`` is not mutated, and the same events at the same instant
    always yield the same context.
    """
    if max_recent_events < 1:
        raise ValueError("max_recent_events must be at least 1")

    reference = as_utc(now)
    risks = prioritize(detect_risks(events, default_rules(reference)))
    recent = [_digest(event) for event in _order_newest_first(events)[:max_recent_events]]
    return BriefContext(
        generated_at=reference,
        event_count=len(events),
        risks=risks,
        recent_events=recent,
        notes=_notes(len(events), risks, len(recent)),
    )
