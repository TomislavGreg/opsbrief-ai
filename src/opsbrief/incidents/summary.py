"""AI incident summaries: the deterministic picture, phrased by a model.

An incident summary reads a disruption back as a short story: what happened, in
what order, and where it stands now. Like a daily brief, it divides its work
strictly. The facts a reader acts on are assembled deterministically from the
incident and its timeline, and a language model is asked only to phrase them.
The model's output is untrusted, so it is constrained to a bounded, single-line
summary that carries no authority to invent an event or change the incident's
state.

This module holds the summary contract. The material the model is shown, and the
generation that produces a summary from it, build on the incident timeline in
:mod:`opsbrief.incidents.timeline`, so a summary traces to the same cited events
the timeline lays out, and a cited identifier with no stored record is reported
as missing here exactly as it is there.
"""

import re
from collections.abc import Iterable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opsbrief.ai import AIProvider, CompletionRequest
from opsbrief.ai.schema import MAX_PROMPT_LENGTH
from opsbrief.events import Event
from opsbrief.incidents.lifecycle import IncidentStatus
from opsbrief.incidents.schema import Incident, IncidentSeverity
from opsbrief.incidents.timeline import (
    IncidentTimeline,
    TimelineEntry,
    build_incident_timeline,
)

#: Upper bound, in characters, on an incident summary's model-phrased text. The
#: summary is untrusted model output, so it is constrained to a bounded length
#: before it is ever carried in a summary.
MAX_INCIDENT_SUMMARY_LENGTH = 1_000

#: Version of the incident-summary output structure. Every summary records the
#: shape it was produced in, so a consumer can tell one structure from a later one
#: and a stored summary stays interpretable after the shape changes. Bump this
#: whenever the fields of :class:`IncidentSummary` change in a way a consumer would
#: need to notice.
INCIDENT_SUMMARY_OUTPUT_VERSION = "incident-summary/1"

#: Version of the prompt an incident summary was produced with: the instructions
#: and the material rendering in this module. Every summary records it, so its
#: prose traces to the exact prompt behind it and a change in phrasing is visible
#: rather than silent. Bump this whenever those instructions or that rendering
#: change.
INCIDENT_SUMMARY_PROMPT_VERSION = "incident-summary-prompt/1"


class IncidentSummary(BaseModel):
    """An incident summarised: the deterministic picture, phrased by a model.

    The summary pairs a model-written ``summary`` with the structured facts behind
    it. Only the ``summary`` comes from a language model, and it is treated as
    untrusted: it is constrained to a bounded length and carries no authority to
    invent an event or move the incident. Everything else is carried straight from
    the incident and its timeline: ``title``, ``status`` and ``severity`` from the
    incident, ``started_at`` and ``ended_at`` from the timeline span,
    ``source_event_ids`` from the incident's cited evidence in cited order, and
    ``missing_event_ids`` from any cited identifier no stored event answered to. So
    a model can rephrase the picture but never change what it says. ``model`` names
    the model that produced the summary, so a generated statement traces to its
    model just as an incident traces to its events. ``output_version`` names the
    shape it was produced in and ``prompt_version`` the prompt that phrased it, so a
    stored summary stays interpretable and a change in structure or phrasing stays
    visible.
    """

    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the incident the summary was built for.",
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="The incident's one-line description, carried over unchanged.",
    )
    status: IncidentStatus = Field(
        description="Where the incident sits in its lifecycle, carried over unchanged.",
    )
    severity: IncidentSeverity = Field(
        description="How serious the incident is, carried over unchanged.",
    )
    summary: str = Field(
        max_length=MAX_INCIDENT_SUMMARY_LENGTH,
        description="The incident in prose, phrased by the model; may be empty.",
    )
    model: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier of the model that produced the summary, for traceability.",
    )
    output_version: str = Field(
        default=INCIDENT_SUMMARY_OUTPUT_VERSION,
        min_length=1,
        max_length=64,
        description="Version of the summary's output structure, so consumers can detect changes.",
    )
    prompt_version: str = Field(
        default=INCIDENT_SUMMARY_PROMPT_VERSION,
        min_length=1,
        max_length=64,
        description="Version of the prompt that produced the summary, so it traces to its prompt.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="When the first cited event occurred, or null when none resolve.",
    )
    ended_at: datetime | None = Field(
        default=None,
        description="When the last cited event occurred, or null when none resolve.",
    )
    source_event_ids: list[str] = Field(
        description="The incident's cited events, in cited order, so the summary traces back.",
    )
    missing_event_ids: list[str] = Field(
        default_factory=list,
        description="Cited identifiers that no stored event answered to, in cited order.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Where the picture is incomplete, for example missing events or no summary.",
    )


#: The task the model performs, phrased by the service. It asks only for prose:
#: the model reads the incident's timeline back as a short story and never decides
#: what it contains. Changing this text, or the material rendering below, is a
#: change of prompt: bump :data:`INCIDENT_SUMMARY_PROMPT_VERSION` when it happens.
DEFAULT_INCIDENT_INSTRUCTIONS = (
    "You are summarising one operational incident for a duty manager. Using only "
    "the incident details and its timeline of events provided, write a short, plain "
    "summary of what happened, in what order, and where the incident stands now. Do "
    "not invent events, numbers or outcomes beyond those given, and do not include "
    "identifiers."
)


_WHITESPACE = re.compile(r"\s+")


def _constrain_summary(text: str) -> str:
    """Reduce untrusted model text to a bounded, single-line summary.

    Whitespace is collapsed so injected line breaks or padding cannot shape the
    summary, and the result is truncated to :data:`MAX_INCIDENT_SUMMARY_LENGTH`, so
    a provider can never make a summary grow without bound.
    """
    collapsed = _WHITESPACE.sub(" ", text).strip()
    if len(collapsed) <= MAX_INCIDENT_SUMMARY_LENGTH:
        return collapsed
    return collapsed[:MAX_INCIDENT_SUMMARY_LENGTH].rstrip()


def _render_entry(entry: TimelineEntry) -> str:
    """Render one timeline event as a single deterministic line of material."""
    status = entry.status.value if entry.status is not None else "unknown"
    return (
        f"- {entry.occurred_at.isoformat()} [{entry.severity.value}] {entry.source} "
        f"{entry.event_type}: {entry.subject} (status: {status})"
    )


def _render_section(title: str, lines: Sequence[str]) -> list[str]:
    """Render a titled block, or a plain 'none' line when it is empty."""
    if not lines:
        return [f"{title}: none."]
    return [f"{title}:", *lines]


def render_incident_material(incident: Incident, timeline: IncidentTimeline) -> str:
    """Render an incident and its timeline as the material shown to the model.

    The rendering is deterministic and bounded: the timeline is already bounded to
    the incident's cited events, and the result is capped at
    :data:`~opsbrief.ai.schema.MAX_PROMPT_LENGTH` so the request the provider
    receives is always well-formed. The span is stated from the timeline, so the
    model is shown the same start and end a reader would see, and missing cited
    events are noted so the model is not misled into implying a complete picture.
    """
    span = "no cited events resolved to a stored record"
    if timeline.started_at is not None and timeline.ended_at is not None:
        span = f"{timeline.started_at.isoformat()} to {timeline.ended_at.isoformat()}"
    lines: list[str] = [
        f"Incident: {incident.title}",
        f"Status: {incident.status.value}",
        f"Severity: {incident.severity.value}",
        f"Span: {span}",
        "",
        *_render_section(
            "Timeline (oldest first)", [_render_entry(entry) for entry in timeline.entries]
        ),
    ]
    if timeline.missing_event_ids:
        missing = len(timeline.missing_event_ids)
        lines += [
            "",
            f"Note: {missing} cited event(s) no longer resolve to a stored record.",
        ]
    rendered = "\n".join(lines)
    if len(rendered) > MAX_PROMPT_LENGTH:
        return rendered[:MAX_PROMPT_LENGTH].rstrip()
    return rendered


def generate_incident_summary(
    incident: Incident,
    events: Iterable[Event],
    provider: AIProvider,
    *,
    instructions: str = DEFAULT_INCIDENT_INSTRUCTIONS,
    max_output_tokens: int = 512,
) -> IncidentSummary:
    """Summarise ``incident`` against ``events``, phrased by ``provider``.

    The incident's cited events are resolved against ``events`` into a timeline,
    the timeline is rendered as material, and the model is asked to phrase it. What
    the model returns is constrained to a bounded, single-line summary; the
    structured facts a reader acts on are taken from the incident and its timeline
    unchanged, so the model rephrases the picture but never changes what it says.

    The summary's ``source_event_ids`` are the incident's cited events in cited
    order, so it traces back to the same evidence the incident does, and any cited
    identifier no stored event answered to is carried in ``missing_event_ids`` and
    noted, so a gap in the evidence is stated plainly rather than implied away.
    """
    timeline = build_incident_timeline(incident, events)
    request = CompletionRequest(
        instructions=instructions,
        input=render_incident_material(incident, timeline),
        max_output_tokens=max_output_tokens,
    )
    notes: list[str] = []
    if timeline.missing_event_ids:
        notes.append(
            f"{len(timeline.missing_event_ids)} cited event(s) no longer resolve "
            "to a stored record."
        )

    response = provider.complete(request)
    summary = _constrain_summary(response.text)
    model = response.model
    if not summary:
        notes.append(
            "The model returned no summary; the incident summary reports the "
            "deterministic picture only."
        )

    return IncidentSummary(
        incident_id=incident.id,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        summary=summary,
        model=model,
        output_version=INCIDENT_SUMMARY_OUTPUT_VERSION,
        prompt_version=INCIDENT_SUMMARY_PROMPT_VERSION,
        started_at=timeline.started_at,
        ended_at=timeline.ended_at,
        source_event_ids=list(incident.event_ids),
        missing_event_ids=timeline.missing_event_ids,
        notes=notes,
    )
