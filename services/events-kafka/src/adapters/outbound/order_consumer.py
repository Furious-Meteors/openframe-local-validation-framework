"""
Kafka consumer adapter for order events.

Subclasses KafkaConsumer[OrderEvent] from openframe-adapters.
The base class handles subscribe(), ack(), nack(), close().

This is the ONLY file in the service that imports from openframe.adapters (consumer side).
"""
from __future__ import annotations

from openframe.adapters.queue.kafka import KafkaConsumer

from src.domain.order_event import OrderEvent


class OrderEventConsumer(KafkaConsumer[OrderEvent]):
    """
    OrderEvent consumer backed by Kafka.

    Inherits from KafkaConsumer[OrderEvent]:
        subscribe(), ack(), nack(), close()

    _deserialise() converts JSON bytes to OrderEvent automatically
    via the base class json.loads() implementation.
    """

    def _deserialise(self, data: bytes) -> OrderEvent:
        """Deserialise JSON bytes from Kafka into an OrderEvent domain object."""
        return OrderEvent.model_validate_json(data)
