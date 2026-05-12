"""FastAPI app entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from pa import __version__
from pa.api.routes import router
from pa.core import get_settings, setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Personal Assistant",
        version=__version__,
        debug=settings.env == "dev",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
