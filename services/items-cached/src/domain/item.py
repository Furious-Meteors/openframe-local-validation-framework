"""Item domain entity — identical to items-postgres."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Item(BaseModel):
    id:          str
    name:        str
    description: Optional[str] = None
    status:      str = "active"
    created_at:  Optional[datetime] = None

    model_config = {"from_attributes": True}
