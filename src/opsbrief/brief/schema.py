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

from opsbrief.brief.actions import NextAction, suggest_next_actions
from opsbrief.events import EventSeverity, EventStatus
from opsbrief.references import SourceReference
from opsbrief.risks import Risk
from opsbrief.warnings import Confidence, GenerationWarning, assess_confidence

#: Upper bound, in characters, on a brief's model-phrased summary. The summary is
#: untrusted model output, so it is constrained to a bounded length before it is
#: ever carried in a brief.
MAX_SUMMARY_LENGTH = 1_000

#: Version of the daily-brief output structure. Every brief records the version of
#: the shape it was produced in, so a consumer can tell one structure from a later
#: one and a stored brief stays interpretable after the shape changes. Bump this
#: whenever the fields of :class:`DailyBrief` change in a way a consumer would
#: need to notice.
BRIEF_OUTPUT_VERSION = "daily-brief/3"

#: Version of the prompt a brief's summary was produced with — the instructions
#: and the context rendering in :mod:`opsbrief.brief.generate`. Every generated
#: brief records it, so a summary traces to the exact prompt behind it and a
#: change in phrasing is visible rather than silent. Bump this whenever those
#: instructions or that rendering change.
BRIEF_PROMPT_VERSION = "brief-prompt/1"


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


def collect_source_event_ids(
    risks: "list[Risk]",
    recent_events: "list[EventDigest]",
) -> list[str]:
    """Return every distinct event id a brief draws on, in citation order.

    The risks' cited events come first, in priority order, then any recent event
    not already cited by a risk. The order is what the eventual brief traces back
    to and the order its source references follow, so both stay in step with each
    other and with the material they summarise.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for risk in risks:
        for event_id in risk.event_ids:
            if event_id not in seen:
                seen.add(event_id)
                ordered.append(event_id)
    for digest in recent_events:
        if digest.id not in seen:
            seen.add(digest.id)
            ordered.append(digest.id)
    return ordered


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
    warnings: list[GenerationWarning] = Field(
        default_factory=list,
        description="The same gaps as structured, machine-readable warnings, in note order.",
    )
    references: list[SourceReference] = Field(
        default_factory=list,
        description="Each source event id resolved to what the event was, in citation order.",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="Every distinct source event id the context draws on.",
    )
    @property
    def source_event_ids(self) -> list[str]:
        """Return every distinct event id the context draws on, in citation order.

        It is derived from ``risks`` and ``recent_events`` rather than stored, so
        it can never disagree with the material it summarises, and it follows the
        same order as ``references`` so the two stay in step.
        """
        return collect_source_event_ids(self.risks, self.recent_events)

    @computed_field(  # type: ignore[prop-decorator]
        description="One suggested next action per risk, in priority order.",
    )
    @property
    def next_actions(self) -> list[NextAction]:
        """Return one suggested next action per risk, in priority order.

        It is derived from ``risks`` rather than stored, so it can never disagree
        with the risks it addresses, and no model takes part: each action is the
        canonical recommendation for the rule behind its risk, carrying the same
        source events.
        """
        return suggest_next_actions(self.risks)


class DailyBrief(BaseModel):
    """A daily operations brief: the deterministic picture, phrased by a model.

    The brief pairs a model-written ``summary`` with the structured facts behind
    it. Only the summary comes from a language model, and it is treated as
    untrusted: it is constrained to a bounded length and carries no authority to
    invent a risk or an event. Everything a reader might act on — the prioritized
    ``risks``, the ``notes`` on where the picture is incomplete, and the
    ``source_event_ids`` every claim traces back to — is carried over unchanged
    from the deterministic :class:`BriefContext`, so a model can rephrase the
    picture but never change what it says. Where the picture is incomplete or
    unphrased, the brief says so twice over: ``notes`` in prose and ``warnings`` as
    structured, machine-readable records, and ``confidence`` sums those warnings
    into a single level a reader can weigh the brief by. Alongside the flat
    ``source_event_ids``, ``references`` resolves each of those ids to what the
    event was, in the same order, so the brief is self-describing and a reader need
    not look every cited event up separately. ``model`` names the model that
    produced the summary, so a generated statement traces to its model just as a
    risk traces to its rule.
    ``output_version`` names the shape the brief was
    produced in, and ``prompt_version`` names the prompt that phrased its summary,
    so a stored or piped brief stays interpretable — and a change in structure or
    phrasing stays visible — after either changes.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(
        description="The reference instant the brief was built for, in UTC.",
    )
    summary: str = Field(
        max_length=MAX_SUMMARY_LENGTH,
        description="The operational picture in prose, phrased by the model; may be empty.",
    )
    model: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier of the model that produced the summary, for traceability.",
    )
    output_version: str = Field(
        default=BRIEF_OUTPUT_VERSION,
        min_length=1,
        max_length=64,
        description="Version of the brief's output structure, so consumers can detect changes.",
    )
    prompt_version: str = Field(
        default=BRIEF_PROMPT_VERSION,
        min_length=1,
        max_length=64,
        description="Version of the prompt that produced the summary, so it traces to its prompt.",
    )
    risks: list[Risk] = Field(
        description="The current risks, most urgent first, carried over from the context.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Where the picture is incomplete, carried over from the context.",
    )
    warnings: list[GenerationWarning] = Field(
        default_factory=list,
        description="The same gaps as structured, machine-readable warnings, in note order.",
    )
    source_event_ids: list[str] = Field(
        default_factory=list,
        description="Every source event id the brief traces back to.",
    )
    references: list[SourceReference] = Field(
        default_factory=list,
        description="Each source event id resolved to what the event was, in the same order.",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="How much of the picture stands, derived from the warnings.",
    )
    @property
    def confidence(self) -> Confidence:
        """Return the confidence the brief's warnings imply.

        It is derived from ``warnings`` rather than stored, so it can never
        disagree with the gaps the brief reports: an all-clear brief is ``high``,
        one merely partial or unphrased is ``medium``, and an empty store is
        ``none``.
        """
        return assess_confidence(self.warnings)
