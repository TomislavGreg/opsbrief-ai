"""The incident contract.

An :class:`Incident` groups the operational events that belong to one
disruption and tracks it through its lifecycle. Unlike a risk, which a rule
recomputes from the current events, an incident is a stateful record: it is
declared once and moves through the states in :mod:`opsbrief.incidents.lifecycle`
as the situation develops.

Two properties carry over from the rest of the product. An incident names the
source event IDs behind it, so it always traces back to real evidence, and its
lifecycle is deterministic: every state change is an allowed move, recorded with
the instant it happened. Language models have no part in either — they may later
phrase an incident summary, but they never declare an incident or move it.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from opsbrief.events.schema import as_utc
from opsbrief.incidents.lifecycle import (
    ACTIVE_STATUSES,
    TERMINAL_STATUSES,
    IncidentStatus,
    InvalidIncidentTransition,
    can_transition,
)


class IncidentSeverity(StrEnum):
    """How serious an incident is.

    An incident is by definition a disruption worth tracking, so there is no
    ``info`` level: the lowest it goes is ``low``, mirroring a risk's severity.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Incident(BaseModel):
    """A tracked operational disruption assembled from stored events.

    ``event_ids`` is the incident's evidence: the identifiers of the stored
    events attributed to it, in the order they were linked, so a reader can look
    each one up. ``opened_at`` is fixed when the incident is declared;
    ``updated_at`` moves with every change; and ``resolved_at`` records when the
    incident stopped being active, set exactly when the status is inactive and
    absent while it is still being worked.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        description="Service-assigned identifier referenced by generated output.",
    )
    title: str = Field(
        min_length=1,
        max_length=200,
        description="One-line human-readable description of the incident.",
    )
    status: IncidentStatus = Field(
        description="Where the incident sits in its lifecycle.",
    )
    severity: IncidentSeverity = Field(
        description="How serious the incident is.",
    )
    opened_at: datetime = Field(
        description="When the incident was declared, in UTC.",
    )
    updated_at: datetime = Field(
        description="When the incident last changed, in UTC.",
    )
    resolved_at: datetime | None = Field(
        default=None,
        description="When the incident stopped being active, set once it is resolved or closed.",
    )
    event_ids: list[str] = Field(
        min_length=1,
        description="Source event IDs behind the incident, in link order, distinct and non-blank.",
    )

    @field_validator("opened_at", "updated_at")
    @classmethod
    def _normalise_required_timestamps(cls, value: datetime) -> datetime:
        return as_utc(value)

    @field_validator("resolved_at")
    @classmethod
    def _normalise_optional_timestamp(cls, value: datetime | None) -> datetime | None:
        return None if value is None else as_utc(value)

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

    @model_validator(mode="after")
    def _check_lifecycle_invariants(self) -> "Incident":
        """Keep the timestamps and the status consistent with each other.

        An active incident has not stopped, so it carries no ``resolved_at``; an
        inactive one has, so it must. Nothing may predate the incident's opening,
        and its resolution cannot come before it opened.
        """
        active = self.status in ACTIVE_STATUSES
        if active and self.resolved_at is not None:
            raise ValueError(f"an active incident ({self.status.value}) has no resolved_at")
        if not active and self.resolved_at is None:
            raise ValueError(f"an inactive incident ({self.status.value}) needs a resolved_at")
        if self.updated_at < self.opened_at:
            raise ValueError("updated_at cannot be before opened_at")
        if self.resolved_at is not None and self.resolved_at < self.opened_at:
            raise ValueError("resolved_at cannot be before opened_at")
        return self

    @computed_field(  # type: ignore[prop-decorator]
        description="Whether the incident is still being worked.",
    )
    @property
    def is_active(self) -> bool:
        """Return whether the incident is in an active state."""
        return self.status in ACTIVE_STATUSES

    @computed_field(  # type: ignore[prop-decorator]
        description="Whether the incident has reached a terminal state.",
    )
    @property
    def is_terminal(self) -> bool:
        """Return whether the incident is closed and can move no further."""
        return self.status in TERMINAL_STATUSES

    @classmethod
    def declare(
        cls,
        *,
        title: str,
        severity: IncidentSeverity,
        event_ids: list[str],
        at: datetime | None = None,
        incident_id: str | None = None,
    ) -> "Incident":
        """Open a new incident from the events that triggered it.

        The incident starts ``open`` with its opening and update instants set to
        ``at`` (the current time by default), and no resolution instant because
        it has only just begun.
        """
        opened = at or datetime.now(UTC)
        return cls(
            id=incident_id or uuid4().hex,
            title=title,
            status=IncidentStatus.OPEN,
            severity=severity,
            opened_at=opened,
            updated_at=opened,
            resolved_at=None,
            event_ids=event_ids,
        )

    def transition_to(self, target: IncidentStatus, *, at: datetime | None = None) -> "Incident":
        """Return a copy of the incident moved to ``target``.

        The move must be one the lifecycle allows, or
        :class:`InvalidIncidentTransition` is raised and nothing changes.
        ``updated_at`` advances to ``at``; ``resolved_at`` is set when the move
        makes the incident inactive and cleared when it makes it active again, so
        the resolution instant always matches the state.
        """
        if not can_transition(self.status, target):
            raise InvalidIncidentTransition(self.status, target)
        moment = at or datetime.now(UTC)
        if target in ACTIVE_STATUSES:
            resolved_at = None
        elif self.resolved_at is not None:
            resolved_at = self.resolved_at
        else:
            resolved_at = moment
        return self.model_copy(
            update={"status": target, "updated_at": moment, "resolved_at": resolved_at}
        )
