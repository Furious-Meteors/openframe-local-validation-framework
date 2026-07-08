"""
ApplicationBootstrap composition root — Stage 2 wiring with THREE adapters.

Canonical proof of ApplicationBootstrap's multi-adapter lifecycle
(configure -> start -> stop, correct shutdown ordering, shutdown_telemetry()
integration) ahead of openframe-cli scaffolding it as the default.

Registration order (= initialisation order):
    1. MongoPlugin   — capability="persistence" — artifact store must be ready first
    2. RedisPlugin   — capability="cache"       — status cache depends on persistence
    3. KafkaPlugin   — capability="queue"       — event bus starts last

Shutdown order (LIFO — reverse of registration, handled by ApplicationBootstrap):
    1. KafkaPlugin  — stop publishing events first
    2. RedisPlugin  — flush cache
    3. MongoPlugin  — close connections last
    4. shutdown_telemetry() — flush the OTel SDK last of all, after ports are down

This ordering ensures:
    - No events are published before artifacts can be stored
    - No status cache reads happen before the database is ready
    - Clean shutdown with no in-flight operations on closed connections
    - Spans emitted during port shutdown are still flushed before the
      TracerProvider itself is torn down
"""
from __future__ import annotations

import asyncio
import logging

from openframe.adapters.db.mongo import MongoPlugin, MongoSettings
from openframe.adapters.db.redis import RedisPlugin, RedisSettings
from openframe.adapters.queue.kafka import KafkaPlugin, KafkaSettings
from openframe.core.runtime import ApplicationBootstrap

from src.adapters.outbound.artifact_kafka_producer import ArtifactEventProducer
from src.adapters.outbound.artifact_mongo_repository import ArtifactMongoRepository

_logger = logging.getLogger(__name__)


class ResearchPipelineApp(ApplicationBootstrap):
    """
    ApplicationBootstrap subclass wiring MongoDB + Redis + Kafka.

    Replaces the module-level ``_registry`` global and ``initialise()``/
    ``shutdown()`` functions that previously lived in ``dependencies.py``.
    """

    def __init__(self) -> None:
        super().__init__()
        self._consumer_task: asyncio.Task | None = None

    def configure(self) -> None:
        """Register all three plugins in the order persistence -> cache -> queue."""
        # 1. MongoDB — artifact persistence.
        # repository_class ensures get_repository() returns ArtifactMongoRepository,
        # not the plain base MongoRepository. Without this, _doc_to_entity()/_entity_to_doc()
        # overrides are silently discarded. See: openframe-adapters CHANGELOG 1.2.0.
        self.register(MongoPlugin(
            MongoSettings(),
            collection="artifacts",
            repository_class=ArtifactMongoRepository,
        ))

        # 2. Redis — status cache.
        self.register(RedisPlugin(RedisSettings()))

        # 3. Kafka — event bus (producer only; consumer started separately).
        # producer_class ensures get_producer() returns ArtifactEventProducer,
        # not the plain base KafkaProducer, so _serialise() override is preserved.
        self.register(KafkaPlugin(
            KafkaSettings(),
            producer_class=ArtifactEventProducer,
        ))

    async def start_consumer(self, task_factory) -> None:
        """
        Start the background Kafka consumer task.

        Called from the FastAPI lifespan after :meth:`start` has completed,
        since the consumer needs the queue port to already be initialised.
        ``task_factory`` is the coroutine function to schedule (kept in the
        entrypoint so the consumer's event-handling logic stays out of the
        composition root).
        """
        self._consumer_task = asyncio.create_task(task_factory())

    async def stop_consumer(self) -> None:
        """Cancel the background Kafka consumer task, if running. Never raises."""
        if self._consumer_task is None:
            return
        self._consumer_task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(self._consumer_task), timeout=5.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        self._consumer_task = None

    async def stop(self) -> None:
        """
        Stop the consumer, shut down all ports, then flush telemetry.

        Order: consumer -> ports (via super().stop(), LIFO) -> shutdown_telemetry().
        shutdown_telemetry() is called AFTER super().stop() so spans emitted
        during port shutdown are still captured and flushed before the
        TracerProvider is torn down.
        """
        await self.stop_consumer()
        await super().stop()
        from openframe.core.telemetry import shutdown_telemetry
        shutdown_telemetry()
        _logger.info("ResearchPipelineApp: all plugins shut down, telemetry flushed.")
