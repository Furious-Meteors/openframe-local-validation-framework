"""
OrderEvent domain entity.

Represents an order lifecycle event published to Kafka.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class OrderEventType(str, Enum):
    CREATED   = "created"
    UPDATED   = "updated"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class OrderEvent(BaseModel):
    """
    An order lifecycle event.

    order_id:    Identifier of the order this event relates to.
    event_type:  The lifecycle transition.
    payload:     Arbitrary event data (amount, user_id, etc.)
    occurred_at: When the event occurred.
    """

    order_id:    str
    event_type:  OrderEventType
    payload:     dict[str, Any] = Field(default_factory=dict)
    occurred_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
