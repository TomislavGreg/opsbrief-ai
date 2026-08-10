"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from opsbrief import __version__
from opsbrief.api import brief, events, health, risks
from opsbrief.config import get_settings
from opsbrief.storage import EventStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hold the event store open for as long as the application is serving.

    The store is opened here rather than while the application object is built
    so that importing this module does not touch the database.
    """
    store = EventStore.open(get_settings().database_url)
    app.state.event_store = store
    try:
        yield
    finally:
        app.state.event_store = None
        store.close()


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
    return app


app = create_app()
