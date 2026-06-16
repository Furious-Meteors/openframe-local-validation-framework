"""
Application-specific repository port.

Defines what the item service needs from persistence —
in domain language, not infrastructure language.

The generic BaseRepository from openframe-core is a platform contract.
This port is the application contract — it can have domain-specific
methods that BaseRepository does not.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.domain.item import Item


@runtime_checkable
class ItemRepositoryPort(Protocol):
    """
    Port defining item persistence from the application's perspective.

    All methods speak domain language — Items, not rows or documents.
    No database imports. No asyncpg. No motor.
    """

    async def get(self, item_id: str) -> Item | None: ...
    async def list(self, limit: int, offset: int) -> tuple[list[Item], int]: ...
    async def create(self, item: Item) -> Item: ...
    async def update(self, item: Item) -> Item | None: ...
    async def delete(self, item_id: str) -> bool: ...
    async def find_by_status(self, status: str) -> list[Item]: ...
    async def bulk_import(self, items: list[Item]) -> int: ...
    async def ping(self) -> bool: ...
    async def is_ready(self) -> bool: ...
