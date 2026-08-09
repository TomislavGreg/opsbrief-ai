"""The daily-brief context contract.

Before a language model phrases a daily brief, the service assembles —
deterministically — the material the brief will draw on: the current risks, a
bounded view of recent operational activity, and notes on where the picture is
incomplete. That assembled material is a :class:`BriefContext`.

The context is derived, never stored, and no model takes part in building it: it
is a pure function of the stored events and the instant they are judged against.
Its whole purpose is to be the trusted, traceable input a provider later turns
into prose, so two properties carry the most weight. Every event the context
draws on is collected in ``source_event_ids``, so the eventual brief traces back
to the evidence, and the context is bounded, so it can never grow a prompt
without limit.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from opsbrief.events import EventSeverity, EventStatus
from opsbrief.risks import Risk


class EventDigest(BaseModel):
    """A stored event reduced to what a brief needs to describe and cite it.

    A digest is intentionally smaller than the stored event: it carries the
    fields a brief describes an event with, and its ``id`` so the brief can cite
    it, but not the free-form ``metadata``. Metadata is left out on purpose —
    keeping the context bounded, and keeping producer-supplied detail out of a
    model prompt until the redaction work of a later phase governs what may be
    shown.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the stored event, so the brief can cite it.",
    )
    source: str = Field(
        min_length=1,
        max_length=64,
        description="System that produced the event, for example 'rostering'.",
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


class BriefContext(BaseModel):
    """The deterministic material a daily brief is built from.

    The context gathers what a duty manager's brief needs to state: the current
    risks in priority order, a bounded view of the most recent operational
    activity, and notes on where the picture is incomplete. It is assembled
    without a language model — a provider later turns it into prose, but never
    decides what it contains — so the same events at the same instant always
    yield the same context.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(
        description="The reference instant the context was assembled at, in UTC.",
    )
    event_count: int = Field(
        ge=0,
        description="How many stored events the context was assembled from.",
    )
    risks: list[Risk] = Field(
        description="The current risks, most urgent first, each citing its rule and events.",
    )
    recent_events: list[EventDigest] = Field(
        description="A bounded view of the most recent events, newest occurred first.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Where the picture is incomplete, for example no events or no risks.",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="Every distinct source event id the context draws on.",
    )
    @property
    def source_event_ids(self) -> list[str]:
        """Return every distinct event id the context draws on.

        The risks' cited events come first, in priority order, then any recent
        event not already cited by a risk. The result is what the eventual brief
        traces back to, so a reader can check every claim against a real event.
        It is derived from ``risks`` and ``recent_events`` rather than stored, so
        it can never disagree with the material it summarises.
        """
        ordered: list[str] = []
        seen: set[str] = set()
        for risk in self.risks:
            for event_id in risk.event_ids:
                if event_id not in seen:
                    seen.add(event_id)
                    ordered.append(event_id)
        for digest in self.recent_events:
            if digest.id not in seen:
                seen.add(digest.id)
                ordered.append(digest.id)
        return ordered
