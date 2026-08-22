"""Structured generation audit records.

A daily brief and an incident summary each pair a model-phrased summary with the
deterministic picture behind it. An audit record is a compact, uniform account of
where one such output came from: what it was produced *from* (the source events it
traces back to, and any cited event that no longer resolved) and *by* (the model
that phrased it and the prompt and output versions it was produced with), together
with how much of the picture stood (the confidence and the warning codes the
output reported).

The record is a projection, not a new judgement: it is derived from an
already-generated output and holds no model involvement of its own, so the same
output always yields the same audit. Its point is uniformity. A brief and an
incident summary carry provenance in slightly different shapes, and a caller that
wants to log or persist "what was generated, from what, and by what" should not
have to special-case each one. A :class:`GenerationAudit` is that single shape.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field

from opsbrief.warnings import Confidence, WarningCode


class GenerationKind(StrEnum):
    """Which kind of generated output an audit record describes.

    A brief is produced over the whole event store, so it audits without a subject;
    an incident summary is produced for one incident, so its audit names that
    incident. The kind lets a consumer branch on the source without inspecting the
    rest of the record.
    """

    #: A daily operations brief, produced over the whole stored event history.
    DAILY_BRIEF = "daily_brief"
    #: An incident summary, produced for one tracked incident.
    INCIDENT_SUMMARY = "incident_summary"


class GenerationAudit(BaseModel):
    """A compact, uniform account of one generated output's provenance.

    The record answers two questions about a generated output. What was it produced
    *from*: ``source_event_ids`` are the events it traces back to, in citation order,
    and ``missing_event_ids`` are any of those a stored event no longer answered to
    at generation. What was it produced *by*: ``model`` is the model that phrased the
    summary and ``prompt_version`` and ``output_version`` are the prompt and shape it
    was produced with. Alongside those, ``confidence`` and ``warning_codes`` record
    how much of the picture stood, carried straight from the output so the audit never
    disagrees with it.

    Every field is copied from an already-generated output, so the record holds no
    model involvement of its own and is a pure function of that output. It is meant to
    be logged or persisted as a small, self-contained provenance trail, uniform across
    the kinds of output it can describe.
    """

    model_config = ConfigDict(extra="forbid")

    kind: GenerationKind = Field(
        description="Which kind of generated output the record describes.",
    )
    subject_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Incident id an incident-summary audit records; null for a brief.",
    )
    model: str = Field(
        min_length=1,
        max_length=128,
        description="Identifier of the model that produced the summary, carried over unchanged.",
    )
    prompt_version: str = Field(
        min_length=1,
        max_length=64,
        description="Version of the prompt the summary was produced with.",
    )
    output_version: str = Field(
        min_length=1,
        max_length=64,
        description="Version of the output structure the record's output was produced in.",
    )
    source_event_ids: list[str] = Field(
        default_factory=list,
        description="Every source event id the output was produced from, in citation order.",
    )
    missing_event_ids: list[str] = Field(
        default_factory=list,
        description="Cited ids no stored event answered to at generation, in citation order.",
    )
    confidence: Confidence = Field(
        description="How much of the picture stood, carried over from the output's warnings.",
    )
    warning_codes: list[WarningCode] = Field(
        default_factory=list,
        description="The gaps the output reported, as machine-readable codes, in order.",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="How many source events the output was produced from.",
    )
    @property
    def source_event_count(self) -> int:
        """Return how many source events the output was produced from.

        It is derived from ``source_event_ids`` rather than stored, so it can never
        disagree with the evidence the record names.
        """
        return len(self.source_event_ids)
