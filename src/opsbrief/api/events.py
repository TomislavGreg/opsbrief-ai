"""Event ingestion endpoint."""

from fastapi import APIRouter, status

from opsbrief.api.dependencies import EventStoreDependency
from opsbrief.events import Event, EventInput
from opsbrief.services import record_event

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
