"""
Session domain entity.

Represents a user session stored in Redis with TTL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class Session(BaseModel):
    """
    A user session.

    id:         Caller-supplied session token.
    user_id:    Owning user identifier.
    created_at: When the session was created.
    expires_at: When the session expires (informational — Redis TTL enforces it).
    metadata:   Optional arbitrary session data.
    """

    id:         str
    user_id:    str
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata:   dict = {}

    model_config = {"from_attributes": True}
