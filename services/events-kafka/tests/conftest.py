from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openframe.core.testing.fixtures import *  # noqa: F401, F403

from src.domain.order_event import OrderEvent, OrderEventType


@pytest.fixture
def event_factory():
    def _make(
        order_id: str = "ord-1",
        event_type: OrderEventType = OrderEventType.CREATED,
        payload: dict | None = None,
    ) -> OrderEvent:
        return OrderEvent(
            order_id=order_id,
            event_type=event_type,
            payload=payload or {"amount": 99.99},
        )
    return _make


@pytest.fixture
def mock_publisher():
    pub = MagicMock()
    pub.publish            = AsyncMock()
    pub.publish_batch      = AsyncMock()
    pub.publish_keyed      = AsyncMock()
    pub.get_topic_metadata = AsyncMock(return_value={
        "topic": "test-topic",
        "partition_count": 1,
        "partition_ids": [0],
        "bootstrap_servers": "localhost:9092",
    })
    pub.close = AsyncMock()
    return pub


@pytest.fixture
def service(mock_publisher):
    from src.application.services.event_service import EventService
    return EventService(mock_publisher)


@pytest.fixture
def mock_kafka_producer():
    p = MagicMock()
    p.start          = AsyncMock()
    p.stop           = AsyncMock()
    p.send_and_wait  = AsyncMock()
    p.flush          = AsyncMock()
    p.partitions_for = MagicMock(return_value={0})
    return p


@pytest.fixture
def mock_settings():
    from openframe.adapters.queue.kafka import KafkaSettings
    return KafkaSettings(
        kafka_bootstrap_servers="localhost:9092",
        kafka_topic="test-topic",
    )


@pytest.fixture
def producer(mock_settings, mock_kafka_producer):
    from src.adapters.outbound.order_producer import OrderEventProducer
    with patch(
        "openframe.adapters.queue.kafka.producer.AIOKafkaProducer",
        return_value=mock_kafka_producer,
    ):
        p = OrderEventProducer(mock_settings)
        p._producer = mock_kafka_producer
        yield p, mock_kafka_producer
