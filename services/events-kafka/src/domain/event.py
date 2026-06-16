from typing import Any, Dict

from pydantic import BaseModel


class OrderEvent(BaseModel):
    order_id: str
    event_type: str
    payload: Dict[str, Any] = {}
