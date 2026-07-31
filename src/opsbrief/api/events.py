"""Event ingestion and retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from opsbrief.api.dependencies import EventStoreDependency
from opsbrief.events import (
    Event,
    EventBatch,
    EventBatchResult,
    EventInput,
    EventPage,
    EventQuery,
)
from opsbrief.services import list_events, record_event, record_events

router = APIRouter(prefix="/events", tags=["events"])


@router.get(
    "",
    response_model=EventPage,
    summary="List stored operational events",
    response_description="A page of stored events, newest first, with the total match count.",
)
def read_events(query: Annotated[EventQuery, Query()], store: EventStoreDependency) -> EventPage:
    """Return a filtered, paginated page of stored events, most recent first.

    The filters and pagination are validated as query parameters; an unknown or
    malformed parameter is rejected with 422 rather than silently ignored.
    """
    return list_events(store, query)


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
