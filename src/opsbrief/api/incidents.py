"""Incident declaration and retrieval endpoints.

The router stays thin: it validates the request, fixes the reference instant at
request time for a declaration, and hands the store to the service. The incident
lifecycle and declaration rules live in the incident package, not here.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from opsbrief.api.dependencies import IncidentStoreDependency
from opsbrief.incidents import (
    Incident,
    IncidentDeclaration,
    IncidentPage,
    IncidentQuery,
)
from opsbrief.services import declare_incident, get_incident, list_incidents

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.get(
    "",
    response_model=IncidentPage,
    summary="List tracked incidents",
    response_description="A page of stored incidents, most recently opened first, with the total.",
)
def read_incidents(
    query: Annotated[IncidentQuery, Query()], store: IncidentStoreDependency
) -> IncidentPage:
    """Return a filtered, paginated page of stored incidents, most recently opened first.

    The status filter and pagination are validated as query parameters; an
    unknown or malformed parameter is rejected with 422 rather than silently
    ignored.
    """
    return list_incidents(store, query)


@router.get(
    "/{incident_id}",
    response_model=Incident,
    summary="Retrieve a tracked incident",
    response_description="The stored incident with the requested identifier.",
    responses={404: {"description": "No incident is stored under the requested identifier."}},
)
def read_incident(
    incident_id: Annotated[
        str, Path(description="The service-assigned identifier of the incident.")
    ],
    store: IncidentStoreDependency,
) -> Incident:
    """Return the single stored incident with ``incident_id``.

    An identifier that matches no stored incident is answered with 404 rather
    than an empty body, so a caller can tell a missing incident from an empty one.
    """
    incident = get_incident(store, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident is stored under id {incident_id!r}",
        )
    return incident


@router.post(
    "",
    response_model=Incident,
    status_code=status.HTTP_201_CREATED,
    summary="Declare a tracked incident",
    response_description="The stored incident, with its service-assigned identifier.",
)
def create_incident(declaration: IncidentDeclaration, store: IncidentStoreDependency) -> Incident:
    """Declare an incident from the request body and store it.

    A body that does not satisfy the declaration contract is rejected with 422
    and nothing is stored. The incident is opened now with a fresh identifier and
    returned with 201, so a caller can track it and read it back by that id.
    """
    return declare_incident(store, declaration, datetime.now(UTC))
