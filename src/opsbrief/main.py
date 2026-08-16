"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opsbrief import __version__
from opsbrief.api import brief, events, health, incidents, risks
from opsbrief.config import get_settings
from opsbrief.storage import EventStore, IncidentStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hold the event and incident stores open while the application is serving.

    The stores are opened here rather than while the application object is built
    so that importing this module does not touch the database. Both address the
    same configured database and are closed again when the application stops.
    """
    database_url = get_settings().database_url
    event_store = EventStore.open(database_url)
    incident_store = IncidentStore.open(database_url)
    app.state.event_store = event_store
    app.state.incident_store = incident_store
    try:
        yield
    finally:
        app.state.event_store = None
        app.state.incident_store = None
        incident_store.close()
        event_store.close()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary=(
            "Turns structured operational events into daily briefs, "
            "risk warnings and incident summaries."
        ),
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(risks.router)
    app.include_router(brief.router)
    app.include_router(incidents.router)
    return app


app = create_app()
