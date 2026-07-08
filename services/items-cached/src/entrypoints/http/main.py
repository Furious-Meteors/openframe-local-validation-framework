"""
FastAPI application entry point — Stage 2 wiring.

PluginRegistry lifecycle managed in lifespan.
Both Postgres and Redis initialised before the app serves traffic.
If either backend is unreachable at startup the app logs a warning
and continues in degraded mode rather than crashing.
"""
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
from src.entrypoints.http.routes import router

load_dotenv()
_logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry()
    record_lifecycle_event("cold_start")

    try:
        await dependencies.initialise()
        _logger.info("items-cached: Postgres and Redis ready")
    except (AdapterConnectionError, ValidationError) as exc:
        _logger.warning(
            "items-cached: one or more backends not ready at startup: %s "
            "— running in degraded mode", exc
        )

    yield

    await dependencies.shutdown()
    _logger.info("items-cached: shutdown complete")
    shutdown_telemetry()


app = FastAPI(
    title="items-cached",
    description="openframe-local-validation — Postgres + Redis multi-adapter (Stage 2)",
    lifespan=lifespan,
)

app.add_middleware(TelemetryMiddleware)
app.include_router(router)


@app.get("/health")
async def health():
    """
    Aggregated health across both adapters.

    Shows Postgres and Redis health separately so you can see
    which backend is degraded if one goes down.
    """
    status = await dependencies.health_all()
    return {
        "status":   "ok",
        "backends": {k: str(v) for k, v in status.items()},
    }


@app.get("/registry")
async def registry_info():
    """
    Shows registered plugins and their capabilities.

    Proves the PluginRegistry is managing both adapters.
    """
    from src.bootstrap.dependencies import _registry
    if _registry is None:
        return {"plugins": [], "wiring": "Stage 2 — PluginRegistry"}
    plugins = _registry.list_plugins()
    return {
        "plugins": [{"capability": p.capability, "name": type(p).__name__} for p in plugins],
        "wiring":  "Stage 2 — PluginRegistry",
    }
