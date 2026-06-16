from __future__ import annotations

import pytest
from src.domain.order_event import OrderEvent, OrderEventType
from src.application.services.event_service import EventService


async def test_publish_event_sets_occurred_at(service, mock_publisher, event_factory):
    event = event_factory()
    await service.publish_event(event)
    published = mock_publisher.publish.call_args[0][0]
    assert published.occurred_at is not None


async def test_publish_event_delegates_to_publisher(service, mock_publisher, event_factory):
    event = event_factory()
    await service.publish_event(event)
    mock_publisher.publish.assert_called_once()


async def test_publish_batch_sets_occurred_at_on_all(service, mock_publisher, event_factory):
    events = [event_factory(order_id=str(i)) for i in range(3)]
    await service.publish_batch(events)
    published = mock_publisher.publish_batch.call_args[0][0]
    assert all(e.occurred_at is not None for e in published)


async def test_publish_keyed_delegates(service, mock_publisher, event_factory):
    event = event_factory()
    await service.publish_keyed("ord-1", event)
    mock_publisher.publish_keyed.assert_called_once()
    call_args = mock_publisher.publish_keyed.call_args[0]
    assert call_args[0] == "ord-1"


async def test_record_received_stores_event(service):
    service.record_received({"order_id": "ord-1", "event_type": "created"})
    received = service.get_received()
    assert len(received) == 1
    assert received[0]["order_id"] == "ord-1"


async def test_get_received_returns_copy(service):
    service.record_received({"order_id": "ord-1"})
    r1 = service.get_received()
    r2 = service.get_received()
    assert r1 == r2
    assert r1 is not r2


async def test_get_topic_metadata_delegates(service, mock_publisher):
    result = await service.get_topic_metadata()
    assert "topic" in result
    mock_publisher.get_topic_metadata.assert_called_once()


async def test_service_no_adapter_imports():
    import ast
    import inspect
    import src.application.services.event_service as m
    source = inspect.getsource(m)
    assert "openframe.adapters" not in source
    tree = ast.parse(source)
    all_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            all_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            all_imports.append(node.module)
    assert not any("aiokafka" in i for i in all_imports), \
        "service imports aiokafka — must be infrastructure-free"
