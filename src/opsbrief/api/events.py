"""Event ingestion endpoint."""

from fastapi import APIRouter, status

from opsbrief.api.dependencies import EventStoreDependency
from opsbrief.events import Event, EventBatch, EventBatchResult, EventInput
from opsbrief.services import record_event, record_events

router = APIRouter(prefix="/events", tags=["events"])


@router.post(
    "",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
    summary="Record an operational event",
    response_description="The stored event, with its service-assigned identifier.",
)
def create_event(payload: EventInput, store: EventStoreDependency) -> Event:
    """Accept one operational event and store it.

    A payload that does not satisfy the event contract is rejected with 422
    and nothing is stored.
    """
    return record_event(store, payload)


@router.post(
    "/batch",
    response_model=EventBatchResult,
    status_code=status.HTTP_201_CREATED,
    summary="Record a batch of operational events",
    response_description="The stored events, with their service-assigned identifiers.",
)
def create_events(batch: EventBatch, store: EventStoreDependency) -> EventBatchResult:
    """Accept a batch of operational events and store them together.

    The batch is validated and stored as a whole: if any event fails the
    contract the request is rejected with 422, and if the batch cannot be
    stored atomically nothing is kept.
    """
    return record_events(store, batch)
