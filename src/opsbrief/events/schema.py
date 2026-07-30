"""The operational event contract.

Producing systems submit :class:`EventInput` payloads. The service turns each
accepted payload into an :class:`Event`, which carries the service-assigned
identifier that briefs, risks and incidents refer back to.

The contract is deliberately generic. Domain specifics belong in ``event_type``
and ``metadata``, not in bespoke fields, so a new producer never requires a
schema change.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_METADATA_ENTRIES = 25
MAX_METADATA_KEY_LENGTH = 64
MAX_METADATA_VALUE_LENGTH = 500

#: Upper bound on a single batch submission, so one request cannot ask the
#: service to validate and store an unbounded number of events at once.
MAX_BATCH_SIZE = 500

#: Metadata is flat and scalar so that stored events stay small and bounded,
#: and so that nothing arbitrary can be nested into a model prompt later.
MetadataValue = str | int | float | bool | None

EventTypeName = Annotated[
    str,
    Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:[._][a-z0-9]+)*$",
        examples=["task.overdue", "shift.unfilled", "integration.failed"],
    ),
]


class EventSeverity(StrEnum):
    """How much attention an event deserves, as stated by its producer."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventStatus(StrEnum):
    """State of the work or system the event describes."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    OVERDUE = "overdue"
    FAILED = "failed"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


def as_utc(value: datetime) -> datetime:
    """Return ``value`` in UTC, rejecting timestamps without an offset.

    A naive timestamp is ambiguous across the deployments that produce events,
    and guessing a timezone would silently distort every downstream schedule
    comparison, so it is refused instead.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return value.astimezone(UTC)


class EventInput(BaseModel):
    """An operational event as submitted by a producing system."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: str = Field(
        min_length=1,
        max_length=64,
        description="System that produced the event, for example 'rostering'.",
    )
    event_type: EventTypeName = Field(
        description="Lowercase dotted name describing what happened.",
    )
    subject: str = Field(
        min_length=1,
        max_length=200,
        description="One-line human-readable description of the event.",
    )
    occurred_at: datetime = Field(
        description="When the event happened. Must carry a timezone offset.",
    )
    severity: EventSeverity = Field(
        default=EventSeverity.INFO,
        description="Producer-stated severity. Risk rules may disagree with it.",
    )
    status: EventStatus | None = Field(
        default=None,
        description="State of the work or system the event describes, when known.",
    )
    entity_type: str | None = Field(
        default=None,
        max_length=64,
        description="Kind of thing the event is about, for example 'fixture'.",
    )
    entity_id: str | None = Field(
        default=None,
        max_length=128,
        description="Identifier of that thing in the producing system.",
    )
    due_at: datetime | None = Field(
        default=None,
        description="Deadline attached to the work, when it has one.",
    )
    external_id: str | None = Field(
        default=None,
        max_length=128,
        description="Producer's own identifier, used to recognise resubmissions.",
    )
    metadata: dict[str, MetadataValue] = Field(
        default_factory=dict,
        description="Flat scalar detail specific to the producing system.",
    )

    @field_validator("occurred_at", "due_at")
    @classmethod
    def _normalise_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else as_utc(value)

    @field_validator("metadata")
    @classmethod
    def _check_metadata(cls, value: dict[str, MetadataValue]) -> dict[str, MetadataValue]:
        if len(value) > MAX_METADATA_ENTRIES:
            raise ValueError(f"metadata may hold at most {MAX_METADATA_ENTRIES} entries")
        for key, item in value.items():
            if not key.strip():
                raise ValueError("metadata keys must not be blank")
            if len(key) > MAX_METADATA_KEY_LENGTH:
                raise ValueError(
                    f"metadata key {key!r} exceeds {MAX_METADATA_KEY_LENGTH} characters"
                )
            if isinstance(item, str) and len(item) > MAX_METADATA_VALUE_LENGTH:
                raise ValueError(
                    f"metadata value for {key!r} exceeds {MAX_METADATA_VALUE_LENGTH} characters"
                )
        return value

    @model_validator(mode="after")
    def _check_entity_pair(self) -> "EventInput":
        if (self.entity_type is None) != (self.entity_id is None):
            raise ValueError("entity_type and entity_id must be given together")
        return self


class Event(EventInput):
    """A stored operational event, identified by the service."""

    id: str = Field(
        min_length=1,
        max_length=64,
        description="Service-assigned identifier referenced by generated output.",
    )
    received_at: datetime = Field(
        description="When the service accepted the event. Must carry a timezone offset.",
    )

    @field_validator("received_at")
    @classmethod
    def _normalise_received_at(cls, value: datetime) -> datetime:
        return as_utc(value)

    @classmethod
    def from_input(cls, payload: EventInput, *, received_at: datetime | None = None) -> "Event":
        """Build a stored event from a validated submission."""
        return cls(
            **payload.model_dump(),
            id=uuid4().hex,
            received_at=received_at or datetime.now(UTC),
        )


class EventBatch(BaseModel):
    """A batch of operational events submitted in one request.

    The batch is bounded and rejected as a whole if any member is invalid, so a
    producer learns about a malformed event before any of the batch is stored.
    """

    model_config = ConfigDict(extra="forbid")

    events: list[EventInput] = Field(
        min_length=1,
        max_length=MAX_BATCH_SIZE,
        description=f"Between 1 and {MAX_BATCH_SIZE} events to store together.",
    )


class EventBatchResult(BaseModel):
    """The stored form of an accepted batch submission."""

    count: int = Field(description="How many events were stored.")
    events: list[Event] = Field(
        description="The stored events, each with its service-assigned identifier.",
    )
