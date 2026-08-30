"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opsbrief import __version__
from opsbrief.api import brief, dashboard, events, health, incidents, risks, webhooks
from opsbrief.config import get_settings
from opsbrief.samples.seed import seed_demo_data
from opsbrief.storage import EventStore, IncidentStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hold the event and incident stores open while the application is serving.

    The stores are opened here rather than while the application object is built
    so that importing this module does not touch the database. Both address the
    same configured database and are closed again when the application stops. When
    demo-data mode is on, an empty store is seeded with synthetic data once the
    stores are open, so a public demo starts with a populated dashboard.
    """
    settings = get_settings()
    event_store = EventStore.open(settings.database_url)
    incident_store = IncidentStore.open(settings.database_url)
    app.state.event_store = event_store
    app.state.incident_store = incident_store
    if settings.demo_data:
        seed_demo_data(event_store, incident_store)
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
    app.include_router(webhooks.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
