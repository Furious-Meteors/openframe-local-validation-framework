"""
FastAPI application entry point.

The background consumer task runs inside lifespan.
It consumes events from Kafka and stores them in the EventService's
in-memory list — observable via GET /events/received.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from openframe.core.middleware import TelemetryMiddleware
from openframe.core.telemetry import record_lifecycle_event, setup_telemetry

from pydantic import ValidationError

from openframe.core.exceptions import AdapterConnectionError

from src.bootstrap import dependencies
from src.entrypoints.http.routes import router

load_dotenv()

_logger = logging.getLogger(__name__)


async def _consumer_task(service) -> None:
    """
    Background task that consumes events from Kafka.

    Creates a fresh KafkaConsumer, subscribes to the topic,
    and calls service.record_received() for each message.

    Runs until the application shuts down (asyncio.CancelledError).
    """
    consumer = dependencies.make_consumer()

    async def handler(event) -> None:
        """Handler called for each received event."""
        _logger.info(
            "Received event: order_id=%s type=%s",
            event.order_id if hasattr(event, "order_id") else "?",
            event.event_type if hasattr(event, "event_type") else "?",
        )
        service.record_received(
            event.model_dump(mode="json")
            if hasattr(event, "model_dump")
            else event
        )

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

    # Start producer — degrade gracefully if Kafka isn't ready yet
    task: asyncio.Task | None = None
    try:
        await dependencies.initialise()
        service = dependencies.get_event_service()
        task = asyncio.create_task(_consumer_task(service))
    except (AdapterConnectionError, ValidationError) as exc:
        _logger.warning(
            "Kafka not ready at startup: %s — running in degraded mode", exc
        )

    yield

    # Shutdown
    if task is not None:
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass

    await dependencies.shutdown()


app = FastAPI(
    title="events-kafka",
    description="openframe-local-validation — Kafka adapter service",
    lifespan=lifespan,
)

app.add_middleware(TelemetryMiddleware)
app.include_router(router)


@app.get("/health")
async def health():
    """
    Health check — verifies producer is started.
    Consumer health is inferred from background task running.
    """
    try:
        service = dependencies.get_event_service()
        metadata = await service.get_topic_metadata()
        return {
            "status":     "ok",
            "topic":      metadata.get("topic"),
            "partitions": metadata.get("partition_count", 0),
        }
    except Exception as exc:
        return {"status": "degraded", "error": str(exc)}
