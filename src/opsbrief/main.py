"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI

from opsbrief import __version__
from opsbrief.api import brief, dashboard, events, health, incidents, risks, webhooks
from opsbrief.api.limits import MaxBodySizeMiddleware
from opsbrief.api.readonly import ReadOnlyMiddleware
from opsbrief.config import get_settings
from opsbrief.samples.seed import seed_demo_data
from opsbrief.startup import configure_logging, validate_settings
from opsbrief.storage import EventStore, IncidentStore


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Hold the event and incident stores open while the application is serving.

    The stores are opened here rather than while the application object is built
    so that importing this module does not touch the database. Both address the
    same configured database and are closed again when the application stops. When
    demo-data mode is on, an empty store is seeded with synthetic data once the
    stores are open, so a public demo starts with a populated dashboard.

    Both stores are entered into one :class:`~contextlib.ExitStack`, and the
    application state is published only once both are open and any seeding has
    succeeded. So if the second open or the seeding fails, the stack closes every
    resource already opened and no partial state is left on the application.
    """
    settings = get_settings()
    with ExitStack() as stack:
        event_store = stack.enter_context(EventStore.open(settings.database_url))
        incident_store = stack.enter_context(IncidentStore.open(settings.database_url))
        if settings.demo_data:
            seed_demo_data(event_store, incident_store)
        app.state.event_store = event_store
        app.state.incident_store = incident_store
        try:
            yield
        finally:
            app.state.event_store = None
            app.state.incident_store = None


def create_app() -> FastAPI:
    """Build and configure the FastAPI application.

    Configuration is validated and logging is wired before the application is
    built, so an unknown provider, excluded field, database URL or log level fails
    here with an actionable error rather than surfacing later as a request-time
    failure or being silently ignored.
    """
    settings = get_settings()
    validate_settings(settings)
    configure_logging(settings)
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary=(
            "Turns structured operational events into daily briefs, "
            "risk warnings and incident summaries."
        ),
        lifespan=lifespan,
    )
    # Bound the bytes of every request body before a router parses it, so a payload
    # is size-limited on all write paths rather than only after Pydantic parsing.
    app.add_middleware(MaxBodySizeMiddleware)
    # In read-only mode refuse every write route up front, so a public demo or a
    # read-only deployment serves reads without taking writes over HTTP. Added last
    # so it wraps outermost and rejects a write before the body is streamed.
    app.add_middleware(ReadOnlyMiddleware, read_only=settings.is_read_only())
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(risks.router)
    app.include_router(brief.router)
    app.include_router(incidents.router)
    app.include_router(webhooks.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
