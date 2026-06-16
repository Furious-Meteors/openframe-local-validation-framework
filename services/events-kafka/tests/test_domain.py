from __future__ import annotations

import pytest
from src.domain.order_event import OrderEvent, OrderEventType


def test_order_event_type_values():
    assert OrderEventType.CREATED.value   == "created"
    assert OrderEventType.UPDATED.value   == "updated"
    assert OrderEventType.CANCELLED.value == "cancelled"
    assert OrderEventType.COMPLETED.value == "completed"


def test_order_event_default_payload():
    e = OrderEvent(order_id="ord-1", event_type=OrderEventType.CREATED)
    assert e.payload == {}


def test_order_event_occurred_at_none_by_default():
    e = OrderEvent(order_id="ord-1", event_type=OrderEventType.CREATED)
    assert e.occurred_at is None


def test_order_event_no_infrastructure_imports():
    import inspect
    import src.domain.order_event as m
    source = inspect.getsource(m)
    assert "aiokafka" not in source
    assert "openframe.adapters" not in source
