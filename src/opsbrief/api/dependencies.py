"""Shared router dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from opsbrief.ai import AIProvider, create_provider
from opsbrief.storage import EventStore, IncidentStore


def get_event_store(request: Request) -> EventStore:
    """Return the event store the running application owns.

    The store is opened when the application starts and closed when it stops,
    so a missing one means the request arrived outside the application
    lifespan rather than that the database is unreachable.
    """
    store: EventStore | None = getattr(request.app.state, "event_store", None)
    if store is None:
        raise RuntimeError("the event store is unavailable: the application has not started up")
    return store


EventStoreDependency = Annotated[EventStore, Depends(get_event_store)]


def get_incident_store(request: Request) -> IncidentStore:
    """Return the incident store the running application owns.

    Like the event store, it is opened when the application starts and closed
    when it stops, so a missing one means the request arrived outside the
    application lifespan rather than that the database is unreachable.
    """
    store: IncidentStore | None = getattr(request.app.state, "incident_store", None)
    if store is None:
        raise RuntimeError("the incident store is unavailable: the application has not started up")
    return store


IncidentStoreDependency = Annotated[IncidentStore, Depends(get_incident_store)]


def get_ai_provider() -> AIProvider:
    """Return the AI provider named by the application settings.

    The provider is built per request from the cached settings rather than held
    on application state: it is a thin, stateless seam over a model, and building
    it fails loudly at request time if the configured name is unknown. A model
    only phrases an already-assembled picture, so nothing about a request depends
    on a provider outliving it.
    """
    return create_provider()


AIProviderDependency = Annotated[AIProvider, Depends(get_ai_provider)]
