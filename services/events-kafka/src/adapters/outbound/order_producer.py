"""
Kafka adapter for event publishing.

Subclasses KafkaProducer[OrderEvent] from openframe-adapters.
Adds domain-specific operations using raw aiokafka.

This is the ONLY file in the service that imports from openframe.adapters (producer side).
"""
from __future__ import annotations

from openframe.adapters.queue.kafka import KafkaProducer

from src.domain.order_event import OrderEvent


class OrderEventProducer(KafkaProducer[OrderEvent]):
    """
    OrderEvent producer backed by Kafka.

    Inherits from KafkaProducer[OrderEvent]:
        publish(), publish_batch(), close(), start()

    _serialise() converts OrderEvent to JSON bytes automatically
    via the base class implementation.

    Adds domain-specific operations:
        publish_keyed()      — keyed publish for partition routing
        get_topic_metadata() — broker topic introspection
    """

    def _serialise(self, event: OrderEvent) -> bytes:
        """Convert OrderEvent to JSON bytes for Kafka. Overrides base class."""
        return event.model_dump_json().encode("utf-8")

    # ── Niche feature 1: Keyed publish ───────────────────────────────────
    # Not in BaseProducer. Routes messages to a specific Kafka partition
    # based on key hash. Messages with same key are always co-located.
    # Accessed via self._producer — raw aiokafka AIOKafkaProducer.

    async def publish_keyed(self, key: str, event: OrderEvent) -> None:
        """
        Publish an event with a partition key.

        Messages with the same key always go to the same partition.
        Useful for ordering guarantees (all events for order-123 in order).

        Not in BaseProducer — raw aiokafka send_and_wait with key param.
        """
        if self._producer is None:
            raise RuntimeError(
                "OrderEventProducer not started. Call await producer.start() first."
            )
        value = self._serialise(event)
        await self._producer.send_and_wait(
            self._settings.kafka_topic,
            value=value,
            key=key.encode("utf-8"),
        )

    # ── Niche feature 2: Topic metadata ──────────────────────────────────
    # Not in BaseProducer. Introspects broker metadata for the topic.
    # Useful for diagnostics and partition count validation.

    async def get_topic_metadata(self) -> dict:
        """
        Get Kafka topic metadata from the broker.

        Uses AIOKafkaProducer.partitions_for() to get partition IDs
        for the configured topic.
        """
        if self._producer is None:
            raise RuntimeError("Producer not started")

        try:
            partitions = self._producer.partitions_for(
                self._settings.kafka_topic
            )
            partition_list = sorted(partitions) if partitions else []
        except Exception:
            partition_list = []

        return {
            "topic":             self._settings.kafka_topic,
            "partition_count":   len(partition_list),
            "partition_ids":     partition_list,
            "bootstrap_servers": self._settings.kafka_bootstrap_servers,
        }
