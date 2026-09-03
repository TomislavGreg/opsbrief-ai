"""Incident declaration and retrieval endpoints.

The router stays thin: it validates the request, fixes the reference instant at
request time for a declaration, and hands the store to the service. The incident
lifecycle and declaration rules live in the incident package, not here.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from opsbrief.api.dependencies import (
    AIProviderDependency,
    EventStoreDependency,
    ExcludedAIContextFieldsDependency,
    IncidentStoreDependency,
)
from opsbrief.incidents import (
    Incident,
    IncidentDeclaration,
    IncidentPage,
    IncidentQuery,
    IncidentResolution,
    IncidentSummary,
    IncidentTimeline,
    IncidentTransition,
    InvalidIncidentTransition,
)
from opsbrief.services import (
    declare_incident,
    get_incident,
    list_incidents,
    report_incident_summary,
    report_incident_timeline,
    resolve_incident,
    transition_incident,
)

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


@router.get(
    "/{incident_id}/summary",
    response_model=IncidentSummary,
    summary="Summarise a tracked incident",
    response_description="The incident summarised: a model summary over the deterministic picture.",
    responses={404: {"description": "No incident is stored under the requested identifier."}},
)
def read_incident_summary(
    incident_id: Annotated[
        str, Path(description="The service-assigned identifier of the incident.")
    ],
    incident_store: IncidentStoreDependency,
    event_store: EventStoreDependency,
    provider: AIProviderDependency,
    excluded_fields: ExcludedAIContextFieldsDependency,
) -> IncidentSummary:
    """Return the summary of the tracked incident with ``incident_id``.

    The incident's cited events are resolved against the whole event history into a
    timeline, and the configured provider phrases that picture into a short summary.
    Everything a reader acts on — the status, severity, span, source event IDs and
    any cited id that no longer resolves — comes from the deterministic picture; only
    the summary comes from the model, and it is constrained as untrusted output, so a
    provider outage degrades the summary rather than failing the request. Any event
    fields a deployment holds back through ``OPSBRIEF_AI_CONTEXT_EXCLUDED_FIELDS`` are
    kept out of the material the model is shown, without changing that picture. An
    identifier that matches no stored incident is answered with 404, so a caller can
    tell a missing incident from one with nothing to describe.
    """
    summary = report_incident_summary(
        incident_store,
        event_store,
        incident_id,
        provider,
        excluded_fields=excluded_fields,
    )
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident is stored under id {incident_id!r}",
        )
    return summary


@router.get(
    "/{incident_id}/timeline",
    response_model=IncidentTimeline,
    summary="Lay a tracked incident out in time",
    response_description="The incident's cited events laid out oldest first, with any gaps named.",
    responses={404: {"description": "No incident is stored under the requested identifier."}},
)
def read_incident_timeline(
    incident_id: Annotated[
        str, Path(description="The service-assigned identifier of the incident.")
    ],
    incident_store: IncidentStoreDependency,
    event_store: EventStoreDependency,
) -> IncidentTimeline:
    """Return the timeline of the tracked incident with ``incident_id``.

    The incident's cited events are resolved against the whole event history and
    laid out oldest first, so the disruption reads forward in time, with the span
    they ran over derived from them. No model takes part: the timeline is a
    deterministic view of the incident and the stored events. A cited id that no
    stored event answers to is named in ``missing_event_ids`` rather than failing
    the request, so a gap in the evidence is stated plainly. An identifier that
    matches no stored incident is answered with 404, so a caller can tell a
    missing incident from one with nothing to lay out.
    """
    timeline = report_incident_timeline(incident_store, event_store, incident_id)
    if timeline is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident is stored under id {incident_id!r}",
        )
    return timeline


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


@router.post(
    "/{incident_id}/resolution",
    response_model=Incident,
    summary="Resolve a tracked incident",
    response_description="The stored incident, now resolved, with any resolution note recorded.",
    responses={
        404: {"description": "No incident is stored under the requested identifier."},
        409: {"description": "The incident cannot move to resolved from its current state."},
    },
)
def resolve_tracked_incident(
    incident_id: Annotated[
        str, Path(description="The service-assigned identifier of the incident.")
    ],
    resolution: IncidentResolution,
    store: IncidentStoreDependency,
) -> Incident:
    """Resolve the incident with ``incident_id``, recording the optional note.

    The incident is moved to ``resolved`` now and saved. A body that does not
    satisfy the contract is rejected with 422. An identifier that matches no
    stored incident is answered with 404, and an incident that cannot move to
    ``resolved`` (already resolved or closed) is answered with 409, so a caller
    can tell a missing incident from one already past resolving.
    """
    try:
        incident = resolve_incident(store, incident_id, resolution, datetime.now(UTC))
    except InvalidIncidentTransition as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident is stored under id {incident_id!r}",
        )
    return incident


@router.post(
    "/{incident_id}/transition",
    response_model=Incident,
    summary="Move a tracked incident to another lifecycle state",
    response_description="The stored incident, now in the requested lifecycle state.",
    responses={
        404: {"description": "No incident is stored under the requested identifier."},
        409: {"description": "The requested move is not allowed from the current state."},
    },
)
def transition_tracked_incident(
    incident_id: Annotated[
        str, Path(description="The service-assigned identifier of the incident.")
    ],
    transition: IncidentTransition,
    store: IncidentStoreDependency,
) -> Incident:
    """Move the incident with ``incident_id`` to ``transition.status``.

    The incident is moved now and saved, so the platform can drive it through the
    whole lifecycle (picking work up as ``investigating``, watching it as
    ``monitoring``, or signing it off as ``closed``), not only resolve it. A body
    that does not satisfy the contract is rejected with 422. An identifier that
    matches no stored incident is answered with 404. A move the lifecycle does not
    allow (a repeat of the current state, or one out of a terminal state) is
    answered with 409, and a note supplied on a move that reopens the incident is
    rejected with 422, so a caller can tell a missing incident from an impossible
    move. Resolving with a note has its own endpoint, ``/resolution``; this one
    reaches every state uniformly.
    """
    now = datetime.now(UTC)
    try:
        incident = transition_incident(store, incident_id, transition, now)
    except InvalidIncidentTransition as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no incident is stored under id {incident_id!r}",
        )
    return incident
