"""FastAPI application entry point."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import ValidationError

from openframe.core.exceptions import AdapterConnectionError
from openframe.core.middleware import TelemetryMiddleware
from openframe.core.telemetry import record_lifecycle_event, setup_telemetry, shutdown_telemetry

from src.bootstrap import dependencies
from src.bootstrap.dependencies import get_session_service
from src.entrypoints.http.routes import router

load_dotenv(override=True)
_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry()
    record_lifecycle_event("cold_start")

    try:
        await dependencies.initialise()
    except (AdapterConnectionError, ValidationError) as exc:
        _logger.warning(
            "cache-redis: Redis not ready at startup: %s "
            "— running in degraded mode", exc
        )

    yield

    await dependencies.shutdown()
    shutdown_telemetry()


app = FastAPI(
    title="cache-redis",
    description="openframe-local-validation — Redis adapter service",
    lifespan=lifespan,
)

app.add_middleware(TelemetryMiddleware)
app.include_router(router)


@app.get("/health")
async def health():
    svc = get_session_service()
    status = await svc.health()
    ok = all(status.values())
    return {"status": "ok" if ok else "degraded", **status}
