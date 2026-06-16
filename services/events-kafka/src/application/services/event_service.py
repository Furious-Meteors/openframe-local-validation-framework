"""Event application service."""
from __future__ import annotations

from datetime import datetime, timezone

from src.application.ports.event_publisher import EventPublisherPort
from src.domain.order_event import OrderEvent


class EventService:
    def __init__(self, publisher: EventPublisherPort) -> None:
        self._publisher = publisher
        # In-memory store of received events — observable via GET /events/received
        self._received: list[dict] = []

    async def publish_event(self, event: OrderEvent) -> None:
        event = event.model_copy(update={
            "occurred_at": datetime.now(timezone.utc)
        })
        await self._publisher.publish(event)

    async def publish_batch(self, events: list[OrderEvent]) -> None:
        now = datetime.now(timezone.utc)
        events = [e.model_copy(update={"occurred_at": now}) for e in events]
        await self._publisher.publish_batch(events)

    async def publish_keyed(self, key: str, event: OrderEvent) -> None:
        """Publish with partition key — same key always goes to same partition."""
        event = event.model_copy(update={
            "occurred_at": datetime.now(timezone.utc)
        })
        await self._publisher.publish_keyed(key, event)

    async def get_topic_metadata(self) -> dict:
        """Topic metadata — niche aiokafka feature."""
        return await self._publisher.get_topic_metadata()

    def record_received(self, event: dict) -> None:
        """Called by the consumer handler to store received events."""
        self._received.append(event)

    def get_received(self) -> list[dict]:
        """Return all events received by the background consumer."""
        return list(self._received)
