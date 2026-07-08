from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import ValidationError

from openframe.core.exceptions import AdapterConnectionError
from openframe.core.middleware import TelemetryMiddleware
from openframe.core.telemetry import record_lifecycle_event, setup_telemetry, shutdown_telemetry

from bootstrap.dependencies import close_backends, init_backends
from entrypoints.http.routes import router

load_dotenv()
_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_telemetry()
    record_lifecycle_event("cold_start")
    try:
        await init_backends()
    except (AdapterConnectionError, ValidationError) as exc:
        _logger.warning(
            "Backend not ready at startup: %s — running in degraded mode", exc
        )
    yield
    await close_backends()
    shutdown_telemetry()


app = FastAPI(title="swap-demo", lifespan=lifespan)
app.add_middleware(TelemetryMiddleware)
app.include_router(router)
