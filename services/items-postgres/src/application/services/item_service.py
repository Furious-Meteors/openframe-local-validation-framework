"""
Item application service.

Contains business logic only. No database imports.
Depends on ItemRepositoryPort — not on PostgresRepository.
"""
from __future__ import annotations

import uuid

from openframe.core.ports import PluginStatus

from src.application.ports.item_repository import ItemRepositoryPort
from src.domain.item import Item


class ItemService:
    """
    Orchestrates item operations.

    Receives ItemRepositoryPort via constructor injection.
    Never imports or instantiates adapters directly.
    """

    def __init__(self, repository: ItemRepositoryPort) -> None:
        self._repo = repository

    async def get_item(self, item_id: str) -> Item | None:
        return await self._repo.get(item_id)

    async def list_items(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[Item], int]:
        return await self._repo.list(limit=limit, offset=offset)

    async def create_item(self, item: Item) -> Item:
        if not item.id:
            item = item.model_copy(update={"id": str(uuid.uuid4())})
        return await self._repo.create(item)

    async def update_item(self, item: Item) -> Item | None:
        return await self._repo.update(item)

    async def delete_item(self, item_id: str) -> bool:
        return await self._repo.delete(item_id)

    async def filter_by_status(self, status: str) -> list[Item]:
        """Domain operation — uses niche feature from the adapter."""
        return await self._repo.find_by_status(status)

    async def bulk_import(self, items: list[Item]) -> int:
        """
        Bulk import using asyncpg COPY protocol.
        Niche feature — not in BaseRepository.
        Dramatically faster than individual INSERTs for large datasets.
        """
        return await self._repo.bulk_import(items)

    async def health(self) -> dict:
        health = await self._repo.health()
        ready = health.status == PluginStatus.READY
        return {"ping": ready, "is_ready": ready}
