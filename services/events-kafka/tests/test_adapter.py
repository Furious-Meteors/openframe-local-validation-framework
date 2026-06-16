from __future__ import annotations

import json
import pytest

from src.adapters.outbound.order_producer import OrderEventProducer
from src.adapters.outbound.order_consumer import OrderEventConsumer
from src.domain.order_event import OrderEvent, OrderEventType

try:
    from openframe.core.ports import BaseProducer, BaseConsumer
    HAS_BASE_CLASSES = True
except ImportError:
    HAS_BASE_CLASSES = False


@pytest.mark.skipif(not HAS_BASE_CLASSES, reason="openframe.core.ports.BaseProducer not available")
def test_producer_satisfies_base_producer(producer):
    p, _ = producer
    assert isinstance(p, BaseProducer)


def test_serialise_produces_json_bytes(producer, event_factory):
    p, _ = producer
    event = event_factory()
    serialised = p._serialise(event)
    assert isinstance(serialised, bytes)
    data = json.loads(serialised.decode("utf-8"))
    assert data["order_id"] == "ord-1"
    assert data["event_type"] == "created"


async def test_publish_calls_send_and_wait(producer, event_factory):
    p, kafka = producer
    event = event_factory()
    await p.publish(event)
    kafka.send_and_wait.assert_called_once()
    call_args = kafka.send_and_wait.call_args
    assert call_args[0][0] == "test-topic"
    # base class may pass value as positional or keyword arg
    value = call_args[1].get("value") if "value" in call_args[1] else call_args[0][1]
    assert b"ord-1" in value


async def test_publish_keyed_passes_key(producer, event_factory):
    p, kafka = producer
    event = event_factory()
    await p.publish_keyed("ord-1", event)
    call_kwargs = kafka.send_and_wait.call_args[1]
    assert call_kwargs["key"] == b"ord-1"


async def test_publish_keyed_raises_when_not_started(mock_settings):
    p = OrderEventProducer(mock_settings)
    p._producer = None
    event = OrderEvent(order_id="o", event_type=OrderEventType.CREATED)
    with pytest.raises(RuntimeError):
        await p.publish_keyed("key", event)


async def test_get_topic_metadata_returns_dict(producer):
    p, kafka = producer
    result = await p.get_topic_metadata()
    assert "topic" in result
    assert "partition_count" in result
    assert result["partition_count"] == 1


async def test_get_topic_metadata_raises_when_not_started(mock_settings):
    p = OrderEventProducer(mock_settings)
    p._producer = None
    with pytest.raises(RuntimeError):
        await p.get_topic_metadata()


@pytest.mark.skipif(not HAS_BASE_CLASSES, reason="openframe.core.ports.BaseConsumer not available")
def test_consumer_satisfies_base_consumer(mock_settings):
    c = OrderEventConsumer(mock_settings)
    assert isinstance(c, BaseConsumer)


def test_consumer_deserialises_json(mock_settings, event_factory):
    c = OrderEventConsumer(mock_settings)
    event = event_factory()
    raw = event.model_dump_json().encode("utf-8")
    result = c._deserialise(raw)
    assert isinstance(result, OrderEvent)
    assert result.order_id == "ord-1"
