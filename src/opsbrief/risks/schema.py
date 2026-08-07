"""The risk contract.

A :class:`Risk` is what a deterministic rule raises when it recognises a
concerning pattern across stored events. Risks are derived, never stored: a
rule recomputes them from the current events, so a risk always reflects the
event history as it stands rather than a snapshot taken earlier.

Two properties are load-bearing for the whole product. A risk names the rule
that raised it, so the reason it exists is never a mystery, and it names the
source event IDs behind it, so every claim traces back to the evidence. The
model enforces both: a risk cannot be built without a rule and at least one
source event.

Language models have no part here. Rules decide what counts as a risk and how
urgent it is; a model may later rephrase a risk, but it never invents one.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator


class RiskSeverity(StrEnum):
    """How urgent a risk is, as decided by the rule that raised it.

    A risk is by definition something that deserves attention, so there is no
    ``info`` level: the lowest a risk goes is ``low``. The severity is the
    rule's judgement, not the producer's, so it may differ from the severity on
    the events behind it.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Risk(BaseModel):
    """A concern raised by a deterministic rule over stored events.

    Every field is set by the rule, never by a producer or a model. ``event_ids``
    is the risk's evidence: the identifiers of the stored events that made the
    rule fire, in the order the rule cites them, so a reader can look each one up.
    """

    model_config = ConfigDict(extra="forbid")

    rule: str = Field(
        min_length=1,
        max_length=64,
        description="Identifier of the rule that raised the risk, for example 'overdue_work'.",
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="One-line human-readable summary of the risk.",
    )
    detail: str = Field(
        min_length=1,
        max_length=1000,
        description="Deterministic explanation of the risk, naming the evidence behind it.",
    )
    severity: RiskSeverity = Field(
        description="How urgent the risk is, decided by the rule rather than the producer.",
    )
    event_ids: list[str] = Field(
        min_length=1,
        description="Source event IDs behind the risk, in cited order, distinct and non-blank.",
    )

    @field_validator("event_ids")
    @classmethod
    def _check_event_ids(cls, value: list[str]) -> list[str]:
        """Reject blank or repeated identifiers so the evidence stays traceable.

        A blank id points at nothing, and a repeated id overstates the evidence,
        so both are refused rather than silently kept.
        """
        seen: set[str] = set()
        for event_id in value:
            if not event_id.strip():
                raise ValueError("event_ids must not contain a blank identifier")
            if event_id in seen:
                raise ValueError(f"event_ids must be unique; {event_id!r} appears more than once")
            seen.add(event_id)
        return value


class RiskList(BaseModel):
    """A snapshot of the risks recognised across the stored events.

    The list is what a risk-list endpoint returns: the current risks in priority
    order, most urgent first, together with the reference instant the rules
    judged against. That instant is part of the answer because risk is
    time-dependent — work overdue now was not overdue an hour ago — so a reader
    knows exactly when the picture was taken. Every risk in the list still names
    the rule and the source events behind it, so the whole snapshot stays
    traceable to the evidence.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime = Field(
        description="The reference instant the rules judged against, in UTC.",
    )
    risks: list[Risk] = Field(
        description="The recognised risks, ordered most urgent first.",
    )

    @computed_field(  # type: ignore[prop-decorator]
        description="How many risks the snapshot holds.",
    )
    @property
    def total(self) -> int:
        """Return the number of risks in the snapshot.

        It is derived from ``risks`` rather than stored, so it can never disagree
        with the list it counts.
        """
        return len(self.risks)
