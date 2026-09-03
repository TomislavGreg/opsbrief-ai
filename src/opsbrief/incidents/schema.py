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

#: Default and maximum page sizes for listing stored incidents, matching the
#: event listing so the two resources page the same way.
DEFAULT_INCIDENT_PAGE_SIZE = 50
MAX_INCIDENT_PAGE_SIZE = 500

#: Upper bound, in characters, on a resolution note. A note is a short operator
#: explanation of how an incident was put right, not a free-form log, so it is
#: length-limited like the rest of the contract.
MAX_RESOLUTION_NOTE_LENGTH = 2_000


def _check_distinct_nonblank_ids(value: list[str]) -> list[str]:
    """Reject blank or repeated identifiers so the evidence stays traceable.

    A blank id points at nothing, and a repeated id overstates the evidence, so
    both are refused rather than silently kept. Shared by the incident model and
    the declaration request body so both apply the same rule.
    """
    seen: set[str] = set()
    for event_id in value:
        if not event_id.strip():
            raise ValueError("event_ids must not contain a blank identifier")
        if event_id in seen:
            raise ValueError(f"event_ids must be unique; {event_id!r} appears more than once")
        seen.add(event_id)
    return value


class IncidentClosedError(ValueError):
    """Raised when an operation would change a closed incident.

    ``closed`` is terminal: a signed-off incident is a finished record, so its
    evidence is frozen and events can be neither linked nor unlinked. It is a
    ``ValueError`` so a caller can treat it as ordinary invalid input, and it
    carries the incident's id and the attempted action so the reason is clear.
    """

    def __init__(self, incident_id: str, action: str) -> None:
        self.incident_id = incident_id
        self.action = action
        super().__init__(f"cannot {action} a closed incident ({incident_id!r})")


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
    absent while it is still being worked. ``resolution_note`` records how the
    incident was put right: it may be attached when the incident moves to an
    inactive state and, like ``resolved_at``, is absent while the incident is
    active and cleared if it reopens.
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
    resolution_note: str | None = Field(
        default=None,
        max_length=MAX_RESOLUTION_NOTE_LENGTH,
        description="How the incident was resolved, recorded when it stops being active.",
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

    @field_validator("resolution_note")
    @classmethod
    def _normalise_resolution_note(cls, value: str | None) -> str | None:
        """Trim surrounding whitespace and treat a blank note as no note.

        A note that is only whitespace says nothing, so it is stored as absent
        rather than as an empty string that a reader would have to special-case.
        """
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("event_ids")
    @classmethod
    def _check_event_ids(cls, value: list[str]) -> list[str]:
        return _check_distinct_nonblank_ids(value)

    @model_validator(mode="after")
    def _check_lifecycle_invariants(self) -> "Incident":
        """Keep the timestamps and the status consistent with each other.

        An active incident has not stopped, so it carries neither a ``resolved_at``
        nor a ``resolution_note``; an inactive one has stopped, so it must record
        when (a note remains optional, since not every resolution is explained).
        Nothing may predate the incident's opening, and its resolution cannot come
        before it opened.
        """
        active = self.status in ACTIVE_STATUSES
        if active and self.resolved_at is not None:
            raise ValueError(f"an active incident ({self.status.value}) has no resolved_at")
        if not active and self.resolved_at is None:
            raise ValueError(f"an inactive incident ({self.status.value}) needs a resolved_at")
        if active and self.resolution_note is not None:
            raise ValueError(f"an active incident ({self.status.value}) has no resolution_note")
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

    def transition_to(
        self,
        target: IncidentStatus,
        *,
        at: datetime | None = None,
        note: str | None = None,
    ) -> "Incident":
        """Return a copy of the incident moved to ``target``.

        The move must be one the lifecycle allows, or
        :class:`InvalidIncidentTransition` is raised and nothing changes.
        ``updated_at`` advances to ``at``; ``resolved_at`` is set when the move
        makes the incident inactive and cleared when it makes it active again, so
        the resolution instant always matches the state.

        ``note`` records how the incident was put right. It is meaningful only for
        a move to an inactive state: a blank note is treated as none, a note given
        on a reopening raises ``ValueError`` (an incident coming back is not being
        resolved), and moving from one inactive state to another (resolved to
        closed) keeps the existing note unless a new one is given. Reopening clears
        the note along with the resolution instant.
        """
        if not can_transition(self.status, target):
            raise InvalidIncidentTransition(self.status, target)
        moment = at or datetime.now(UTC)
        cleaned_note = note.strip() if note is not None else ""
        if len(cleaned_note) > MAX_RESOLUTION_NOTE_LENGTH:
            raise ValueError(
                f"a resolution note may be at most {MAX_RESOLUTION_NOTE_LENGTH} characters"
            )
        if target in ACTIVE_STATUSES:
            if cleaned_note:
                raise ValueError("a resolution note cannot be recorded when reopening an incident")
            resolved_at = None
            resolution_note = None
        else:
            resolved_at = self.resolved_at if self.resolved_at is not None else moment
            resolution_note = cleaned_note or self.resolution_note
        return self.model_copy(
            update={
                "status": target,
                "updated_at": moment,
                "resolved_at": resolved_at,
                "resolution_note": resolution_note,
            }
        )

    def link_events(self, event_ids: list[str], *, at: datetime | None = None) -> "Incident":
        """Return a copy of the incident with ``event_ids`` attributed to it.

        New identifiers are appended after the ones already linked, in the order
        given; an identifier already linked is left where it is, so linking is
        idempotent and never reorders or duplicates the evidence. ``updated_at``
        advances to ``at``. A closed incident is frozen, so linking to one raises
        :class:`IncidentClosedError` and nothing changes.
        """
        if self.is_terminal:
            raise IncidentClosedError(self.id, "link events to")
        merged = list(self.event_ids)
        for event_id in event_ids:
            if not event_id.strip():
                raise ValueError("event_ids must not contain a blank identifier")
            if event_id not in merged:
                merged.append(event_id)
        moment = at or datetime.now(UTC)
        return self.model_copy(update={"event_ids": merged, "updated_at": moment})

    def unlink_events(self, event_ids: list[str], *, at: datetime | None = None) -> "Incident":
        """Return a copy of the incident with ``event_ids`` no longer attributed.

        Identifiers not currently linked are ignored, so unlinking is idempotent.
        An incident must always cite at least one source event, so an unlink that
        would remove the last of them raises ``ValueError`` and nothing changes;
        a closed incident is frozen, so unlinking from one raises
        :class:`IncidentClosedError`. ``updated_at`` advances to ``at``.
        """
        if self.is_terminal:
            raise IncidentClosedError(self.id, "unlink events from")
        removing = set(event_ids)
        remaining = [event_id for event_id in self.event_ids if event_id not in removing]
        if not remaining:
            raise ValueError("an incident must keep at least one source event")
        moment = at or datetime.now(UTC)
        return self.model_copy(update={"event_ids": remaining, "updated_at": moment})


class IncidentDeclaration(BaseModel):
    """A request to declare a new incident from the events behind it.

    This is the body a caller posts to open an incident: the parts a person
    decides (a title, how serious it is, and the source events it groups). The
    service assigns the identifier and the timestamps and starts the incident
    ``open``, so those are not part of the request. Unknown fields are rejected
    so a mistyped body fails loudly rather than being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        min_length=1,
        max_length=200,
        description="One-line human-readable description of the incident.",
    )
    severity: IncidentSeverity = Field(
        description="How serious the incident is.",
    )
    event_ids: list[str] = Field(
        min_length=1,
        description="Source event IDs behind the incident, in link order, distinct and non-blank.",
    )

    @field_validator("event_ids")
    @classmethod
    def _check_event_ids(cls, value: list[str]) -> list[str]:
        return _check_distinct_nonblank_ids(value)


class IncidentResolution(BaseModel):
    """A request to resolve a tracked incident, optionally recording how.

    This is the body a caller posts to move an incident to ``resolved``. The
    ``note`` is optional but recommended: it explains how the incident was put
    right and is carried into the incident's record and its summary. A blank note
    is treated as none. Unknown fields are rejected so a mistyped body fails
    loudly rather than being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(
        default=None,
        max_length=MAX_RESOLUTION_NOTE_LENGTH,
        description="How the incident was resolved; optional but recommended.",
    )

    @field_validator("note")
    @classmethod
    def _normalise_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class IncidentTransition(BaseModel):
    """A request to move a tracked incident to another lifecycle state.

    This is the body a caller posts to drive an incident through its lifecycle:
    the target ``status`` to move to, and an optional ``note`` recording how the
    incident was put right when the move ends it (resolved or closed). The allowed
    moves are the incident lifecycle's, so a move it does not permit is refused
    rather than applied, and a note carries only on a move to an inactive state.
    Unknown fields are rejected so a mistyped body fails loudly rather than being
    silently dropped.
    """

    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus = Field(
        description="The lifecycle state to move the incident to.",
    )
    note: str | None = Field(
        default=None,
        max_length=MAX_RESOLUTION_NOTE_LENGTH,
        description="How the incident was put right; recorded only on a move that ends it.",
    )

    @field_validator("note")
    @classmethod
    def _normalise_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class IncidentQuery(BaseModel):
    """Filters and pagination for listing stored incidents.

    The status and severity filters are optional and match the incident's
    lifecycle state and severity exactly; ``opened_from`` and ``opened_to`` narrow
    the listing to incidents opened within that inclusive window. An omitted
    filter does not narrow the result. Unknown fields are rejected so a mistyped
    filter fails loudly instead of being silently ignored and returning the wrong
    page.
    """

    model_config = ConfigDict(extra="forbid")

    status: IncidentStatus | None = Field(
        default=None,
        description="Return only incidents in this lifecycle state.",
    )
    severity: IncidentSeverity | None = Field(
        default=None,
        description="Return only incidents of this severity.",
    )
    opened_from: datetime | None = Field(
        default=None,
        description="Return only incidents opened at or after this time. Needs a timezone offset.",
    )
    opened_to: datetime | None = Field(
        default=None,
        description="Return only incidents opened at or before this time. Needs a timezone offset.",
    )
    limit: int = Field(
        default=DEFAULT_INCIDENT_PAGE_SIZE,
        ge=1,
        le=MAX_INCIDENT_PAGE_SIZE,
        description=f"How many incidents to return, between 1 and {MAX_INCIDENT_PAGE_SIZE}.",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="How many matching incidents to skip before the page begins.",
    )

    @field_validator("opened_from", "opened_to")
    @classmethod
    def _normalise_bounds(cls, value: datetime | None) -> datetime | None:
        return None if value is None else as_utc(value)

    @model_validator(mode="after")
    def _check_bound_order(self) -> "IncidentQuery":
        if (
            self.opened_from is not None
            and self.opened_to is not None
            and self.opened_from > self.opened_to
        ):
            raise ValueError("opened_from must not be later than opened_to")
        return self


class IncidentPage(BaseModel):
    """One page of stored incidents matching a listing query."""

    total: int = Field(
        description="How many stored incidents match the filter, across all pages.",
    )
    limit: int = Field(description="The page size the listing was taken with.")
    offset: int = Field(description="How many matching incidents were skipped.")
    incidents: list[Incident] = Field(
        description="The incidents in this page, most recently opened first.",
    )
