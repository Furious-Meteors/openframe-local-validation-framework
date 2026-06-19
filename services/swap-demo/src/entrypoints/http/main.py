import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from pydantic import ValidationError

from bootstrap.dependencies import close_backends, init_backends
from entrypoints.http.routes import router

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        await init_backends()
    except (ValidationError, OSError) as exc:
        _logger.warning(
            "Backend not ready at startup: %s — running in degraded mode", exc
        )
    yield
    await close_backends()


app = FastAPI(title="swap-demo", lifespan=lifespan)
app.include_router(router)
