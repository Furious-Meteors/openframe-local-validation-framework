"""Application port for event publishing."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventPublisherPort(Protocol):
    async def publish(self, message: dict[str, Any]) -> None: ...
    async def close(self) -> None: ...
