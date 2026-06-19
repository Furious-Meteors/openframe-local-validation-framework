"""
Composition root — Stage 2 wiring with THREE adapters.

This is the most complete PluginRegistry example in the validation suite.
Three plugins, three capabilities, one registry.

Registration order (= initialisation order):
    1. MongoPlugin   — capability="persistence" — artifact store must be ready first
    2. RedisPlugin   — capability="cache"       — status cache depends on persistence
    3. KafkaPlugin   — capability="queue"       — event bus starts last

Shutdown order (LIFO — reverse of registration):
    1. KafkaPlugin  — stop publishing events first
    2. RedisPlugin  — flush cache
    3. MongoPlugin  — close connections last

This ordering ensures:
    - No events are published before artifacts can be stored
    - No status cache reads happen before the database is ready
    - Clean shutdown with no in-flight operations on closed connections
"""
from __future__ import annotations

import asyncio
import logging

from openframe.adapters.db.mongo    import MongoPlugin, MongoSettings
from openframe.adapters.db.redis    import RedisPlugin, RedisSettings
from openframe.adapters.queue.kafka import KafkaPlugin, KafkaSettings
from openframe.core.plugins         import PluginRegistry
from openframe.core.tracing         import TracingProxy

from src.adapters.outbound.artifact_mongo_repository import ArtifactMongoRepository
from src.adapters.outbound.artifact_redis_cache      import ArtifactRedisCache
from src.adapters.outbound.artifact_kafka_producer   import ArtifactEventProducer
from src.application.services.pipeline_service       import ResearchPipelineService

_logger   = logging.getLogger(__name__)
_registry: PluginRegistry | None = None

# Background consumer task handle
_consumer_task: asyncio.Task | None = None


async def initialise() -> None:
    """
    Register and initialise all three plugins.

    Called once in FastAPI lifespan on startup.
    All three backends must be healthy before the app serves traffic.
    """
    global _registry

    _registry = PluginRegistry()

    # 1. MongoDB — artifact persistence
    # repository_class ensures get_repository() returns ArtifactMongoRepository,
    # not the plain base MongoRepository. Without this, _doc_to_entity()/_entity_to_doc()
    # overrides are silently discarded. See: openframe-adapters CHANGELOG 1.2.0.
    _registry.register(MongoPlugin(
        MongoSettings(),
        collection="artifacts",
        repository_class=ArtifactMongoRepository,
    ))

    # 2. Redis — status cache
    _registry.register(RedisPlugin(RedisSettings()))

    # 3. Kafka — event bus (producer only; consumer started separately)
    # producer_class ensures get_producer() returns ArtifactEventProducer,
    # not the plain base KafkaProducer, so _serialise() override is preserved.
    _registry.register(KafkaPlugin(
        KafkaSettings(),
        producer_class=ArtifactEventProducer,
    ))

    # Initialise all — raises if any backend is unreachable
    await _registry.initialize_all()
    _logger.info("All three plugins initialised: MongoDB, Redis, Kafka")


async def shutdown() -> None:
    """
    Shut down all plugins in reverse order.
    Stop the background consumer task first.
    Never raises.
    """
    global _consumer_task

    # Cancel background consumer
    if _consumer_task is not None:
        _consumer_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(_consumer_task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        _consumer_task = None

    if _registry is not None:
        await _registry.shutdown_all()
        _logger.info("All plugins shut down.")


async def health_all() -> dict:
    if _registry is None:
        return {}
    return await _registry.health_all()


def get_pipeline_service() -> ResearchPipelineService:
    """
    FastAPI dependency.

    Builds ResearchPipelineService from three plugin-backed adapters.
    Each adapter wrapped with TracingProxy for automatic OTel spans.

    Capability lookup:
        "persistence" → MongoPlugin  → ArtifactMongoRepository
        "cache"       → RedisPlugin  → ArtifactRedisCache
        "queue"       → KafkaPlugin  → ArtifactEventProducer
    """
    if _registry is None:
        raise RuntimeError("PluginRegistry not initialised.")

    persistence = TracingProxy(
        _registry.get("persistence").get_repository(),
        prefix="repository.artifact.mongo",
    )
    cache = TracingProxy(
        _registry.get("cache").get_repository(),
        prefix="repository.artifact.redis",
    )
    producer = _registry.get("queue").get_producer()

    return ResearchPipelineService(
        persistence=persistence,
        cache=cache,
        publisher=producer,
    )


def make_consumer():
    """Create a fresh Kafka consumer for the background task."""
    if _registry is None:
        raise RuntimeError("PluginRegistry not initialised.")
    return _registry.get("queue").make_consumer()
