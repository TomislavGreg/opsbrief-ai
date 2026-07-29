"""Shared router dependencies."""

from typing import Annotated

from fastapi import Depends, Request

from opsbrief.storage import EventStore


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
