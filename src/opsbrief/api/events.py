"""Event ingestion and retrieval endpoints."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from opsbrief.api.dependencies import EventStoreDependency, SensitiveMetadataKeysDependency
from opsbrief.events import (
    Event,
    EventBatch,
    EventBatchResult,
    EventInput,
    EventPage,
    EventQuery,
)
from opsbrief.services import get_event, list_events, record_event, record_events

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


@router.get(
    "/{event_id}",
    response_model=Event,
    summary="Retrieve a stored operational event",
    response_description="The stored event with the requested identifier.",
    responses={404: {"description": "No event is stored under the requested identifier."}},
)
def read_event(
    event_id: Annotated[str, Path(description="The service-assigned identifier of the event.")],
    store: EventStoreDependency,
) -> Event:
    """Return the single stored event with ``event_id``.

    An identifier that matches no stored event is answered with 404 rather than
    an empty body, so a caller can tell a missing event from an empty one.
    """
    event = get_event(store, event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no event is stored under id {event_id!r}",
        )
    return event


@router.post(
    "",
    response_model=Event,
    status_code=status.HTTP_201_CREATED,
    summary="Record an operational event",
    response_description="The stored event, with its service-assigned identifier.",
    responses={
        200: {"description": "The event was recognised as a resubmission and not stored again."}
    },
)
def create_event(
    payload: EventInput,
    store: EventStoreDependency,
    sensitive_keys: SensitiveMetadataKeysDependency,
    response: Response,
) -> Event:
    """Accept one operational event and store it.

    A payload that does not satisfy the event contract is rejected with 422
    and nothing is stored. A submission whose ``external_id`` the same source
    has already sent is recognised as a resubmission: the originally stored
    event is returned with 200 rather than stored again, so retrying a delivery
    is safe. A newly stored event is returned with 201. Sensitive metadata
    values are masked before storage.
    """
    event, created = record_event(store, payload, sensitive_keys=sensitive_keys)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return event


@router.post(
    "/batch",
    response_model=EventBatchResult,
    status_code=status.HTTP_201_CREATED,
    summary="Record a batch of operational events",
    response_description="The stored events, with their service-assigned identifiers.",
)
def create_events(
    batch: EventBatch,
    store: EventStoreDependency,
    sensitive_keys: SensitiveMetadataKeysDependency,
) -> EventBatchResult:
    """Accept a batch of operational events and store them together.

    The batch is validated and stored as a whole: if any event fails the
    contract the request is rejected with 422, and if the batch cannot be
    stored atomically nothing is kept. Sensitive metadata values are masked
    before storage.
    """
    return record_events(store, batch, sensitive_keys=sensitive_keys)
