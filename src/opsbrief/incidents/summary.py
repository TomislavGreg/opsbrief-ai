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

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from opsbrief.incidents.lifecycle import IncidentStatus
from opsbrief.incidents.schema import IncidentSeverity

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
