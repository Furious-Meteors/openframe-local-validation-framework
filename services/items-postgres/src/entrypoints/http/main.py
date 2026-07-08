"""
FastAPI application entry point.

Loads env vars, bootstraps telemetry, adds middleware.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from openframe.core.middleware import TelemetryMiddleware
from openframe.core.telemetry import record_lifecycle_event, setup_telemetry, shutdown_telemetry

from src.bootstrap.dependencies import _get_settings, get_item_service
from src.entrypoints.http.routes import router

load_dotenv(override=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry()
    record_lifecycle_event("cold_start")
    # Eagerly validate settings at startup — fail fast if DATABASE_URL missing
    _get_settings()
    yield
    shutdown_telemetry()


app = FastAPI(
    title="items-postgres",
    description="openframe-local-validation — Postgres adapter service",
    lifespan=lifespan,
)

app.add_middleware(TelemetryMiddleware)
app.include_router(router)


@app.get("/health")
async def health():
    svc = get_item_service()
    status = await svc.health()
    ok = all(status.values())
    return {"status": "ok" if ok else "degraded", **status}
