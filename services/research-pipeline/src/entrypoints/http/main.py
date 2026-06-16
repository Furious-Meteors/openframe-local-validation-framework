"""
FastAPI application entry point.

Three-plugin PluginRegistry lifecycle managed in lifespan.
Background Kafka consumer started after all plugins initialise.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from openframe.core.middleware import TelemetryMiddleware
from openframe.core.telemetry import record_lifecycle_event, setup_telemetry

from src.bootstrap import dependencies
from src.entrypoints.http.routes import router

load_dotenv()
_logger = logging.getLogger(__name__)


async def _consumer_task() -> None:
    """
    Background task — consumes artifact events from Kafka.

    Receives artifact.ingested events and updates status in Redis.
    Runs until cancelled on shutdown.
    """
    consumer = dependencies.make_consumer()

    async def handler(event: dict) -> None:
        event_type   = event.get("event_type", "")
        artifact_id  = event.get("artifact_id", "")
        _logger.info("Received event: %s for artifact %s", event_type, artifact_id)

        if event_type == "artifact.ingested" and artifact_id:
            svc = dependencies.get_pipeline_service()
            from src.domain.artifact import EmbeddingStatus
            await svc.update_status(artifact_id, EmbeddingStatus.PROCESSING)
            _logger.info("Status updated to PROCESSING for %s", artifact_id)

    try:
        await consumer.subscribe(handler)
    except asyncio.CancelledError:
        pass
    except Exception as exc:
        _logger.error("Consumer error: %s", exc)
    finally:
        await consumer.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_telemetry()
    record_lifecycle_event("cold_start")

    # Initialise all three plugins — fails fast if any backend is down
    await dependencies.initialise()
    _logger.info("research-pipeline: all adapters ready")

    # Start background Kafka consumer
    dependencies._consumer_task = asyncio.create_task(_consumer_task())

    yield

    # Shutdown — consumer cancelled, all plugins shut down in LIFO order
    await dependencies.shutdown()
    _logger.info("research-pipeline: shutdown complete")


app = FastAPI(
    title="research-pipeline",
    description="openframe-local-validation — MongoDB + Redis + Kafka (Stage 2, 3 adapters)",
    lifespan=lifespan,
)

app.add_middleware(TelemetryMiddleware)
app.include_router(router)


@app.get("/health")
async def health():
    """Aggregated health across all three adapters."""
    plugin_health = await dependencies.health_all()
    return {
        "status": "ok",
        "adapters": {k: str(v) for k, v in plugin_health.items()},
    }


@app.get("/pipeline-info")
async def pipeline_info():
    """
    Shows the three-adapter pipeline configuration.

    Confirms:
    - Which plugins are registered
    - What capability each provides
    - The startup ordering
    """
    return {
        "service": "research-pipeline",
        "adapters": [
            {"order": 1, "capability": "persistence", "backend": "MongoDB",
             "role": "artifact store — source of truth"},
            {"order": 2, "capability": "cache",       "backend": "Redis",
             "role": "status cache — fast reads"},
            {"order": 3, "capability": "queue",       "backend": "Kafka",
             "role": "event bus — async processing"},
        ],
        "wiring": "Stage 2 — PluginRegistry",
        "pattern": "ingest → store (mongo) → publish (kafka) → cache status (redis)",
    }
