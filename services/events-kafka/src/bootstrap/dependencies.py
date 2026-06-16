"""
Composition root — Stage 1 wiring.

One adapter (Kafka) → direct construction.
Producer is long-lived (started in lifespan).
Consumer is created fresh per subscribe() session.

Note: KafkaPlugin.capability = "queue".
"""
from __future__ import annotations

from openframe.adapters.queue.kafka import KafkaSettings

from src.adapters.outbound.order_consumer import OrderEventConsumer
from src.adapters.outbound.order_producer import OrderEventProducer
from src.application.services.event_service import EventService

_settings: KafkaSettings | None = None
_producer: OrderEventProducer | None = None
_service:  EventService | None = None


async def initialise() -> None:
    """
    Start the Kafka producer. Called once in lifespan.

    Producer is long-lived — start once, publish many.
    Consumer is created fresh per subscribe() call in the background task.
    """
    global _settings, _producer, _service

    _settings = KafkaSettings()
    _producer = OrderEventProducer(_settings)
    await _producer.start()

    _service = EventService(_producer)


async def shutdown() -> None:
    """Stop the producer. Never raises."""
    global _producer
    if _producer is not None:
        await _producer.close()
        _producer = None


def get_event_service() -> EventService:
    """FastAPI dependency."""
    if _service is None:
        raise RuntimeError("EventService not initialised. Call initialise() first.")
    return _service


def make_consumer() -> OrderEventConsumer:
    """Create a fresh consumer for a subscribe session."""
    if _settings is None:
        raise RuntimeError("Settings not initialised.")
    return OrderEventConsumer(_settings)
