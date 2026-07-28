"""FastAPI application entry point."""

from fastapi import FastAPI

from opsbrief import __version__
from opsbrief.api import health
from opsbrief.config import get_settings


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
    )
    app.include_router(health.router)
    return app


app = create_app()
