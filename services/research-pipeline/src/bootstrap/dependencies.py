"""
Composition root — Stage 2 wiring with THREE adapters.

This is the FastAPI dependency layer. Together with
:class:`~src.bootstrap.app.ResearchPipelineApp` (ApplicationBootstrap, which
owns the actual plugin registration in its configure()), ``bootstrap/`` is
the only package that imports from openframe.adapters. This module provides
``Depends()``-friendly functions that read from the module-level ``_app``
instance instead of owning the port registry directly.

Registration order (= initialisation order, defined in app.py's configure()):
    1. MongoPlugin   — capability="persistence" — artifact store must be ready first
    2. RedisPlugin   — capability="cache"       — status cache depends on persistence
    3. KafkaPlugin   — capability="queue"       — event bus starts last

Shutdown order (LIFO — reverse of registration, handled by ApplicationBootstrap.stop()):
    1. KafkaPlugin  — stop publishing events first
    2. RedisPlugin  — flush cache
    3. MongoPlugin  — close connections last
    4. shutdown_telemetry() — flush OTel SDK last of all
"""
from __future__ import annotations

import logging

from openframe.core.ports   import Capability
from openframe.core.tracing import TracingProxy

from src.application.services.pipeline_service import ResearchPipelineService
from src.bootstrap.app import ResearchPipelineApp

_logger = logging.getLogger(__name__)

_app: ResearchPipelineApp = ResearchPipelineApp()


async def initialise() -> None:
    """
    Configure and initialise all three plugins.

    Called once per FastAPI lifespan startup. Rebuilds ``_app`` fresh each
    call so repeated startup/shutdown cycles (e.g. one per test TestClient)
    never re-register plugins into an already-populated registry.
    All three backends must be healthy before the app serves traffic.
    The background consumer is started separately via start_consumer() once
    the caller has its handler coroutine ready.
    """
    global _app
    _app = ResearchPipelineApp()
    await _app.start()
    _logger.info("All three plugins initialised: MongoDB, Redis, Kafka")


async def start_consumer(task_factory) -> None:
    """Start the background Kafka consumer task. Delegates to the app instance."""
    await _app.start_consumer(task_factory)


async def shutdown() -> None:
    """
    Stop the background consumer, shut down all plugins in reverse order,
    then flush telemetry. Never raises.
    """
    await _app.stop()
    _logger.info("All plugins shut down.")


async def health_all() -> dict:
    return await _app.health()


def get_pipeline_service() -> ResearchPipelineService:
    """
    FastAPI dependency.

    Builds ResearchPipelineService from three plugin-backed adapters.
    Each adapter wrapped with TracingProxy for automatic OTel spans.

    Capability lookup:
        Capability.PERSISTENCE → MongoPlugin  → ArtifactMongoRepository
        Capability.CACHE       → RedisPlugin  → ArtifactRedisCache
        Capability.QUEUE       → KafkaPlugin  → ArtifactEventProducer
    """
    persistence = TracingProxy(
        _app.get(Capability.PERSISTENCE).get_repository(),
        prefix="repository.artifact.mongo",
    )
    cache = TracingProxy(
        _app.get(Capability.CACHE).get_repository(),
        prefix="repository.artifact.redis",
    )
    producer = TracingProxy(
        _app.get(Capability.QUEUE).get_producer(),
        prefix="queue.event",
    )

    return ResearchPipelineService(
        persistence=persistence,
        cache=cache,
        publisher=producer,
    )


def make_consumer():
    """Create a fresh Kafka consumer for the background task."""
    return _app.get(Capability.QUEUE).make_consumer()
