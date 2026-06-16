"""
Item domain entity.

Pure Python — no database, no framework imports.
The centre of the hexagonal architecture.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Item(BaseModel):
    """
    An item in the system.

    id:          Caller-supplied unique identifier (UUID or slug).
    name:        Human-readable item name. Required, non-empty.
    description: Optional longer description.
    status:      Lifecycle status. Default 'active'.
    created_at:  Set by the database on insert.
    """

    id: str
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
