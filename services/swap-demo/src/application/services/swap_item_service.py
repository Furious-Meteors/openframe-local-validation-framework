from typing import List, Optional

from application.ports.swap_item_repository import SwapItemRepository
from domain.swap_item import SwapItem


class SwapItemService:
    def __init__(self, repo: SwapItemRepository) -> None:
        self._repo = repo

    async def create(self, item: SwapItem) -> SwapItem:
        await self._repo.save(item)
        return item

    async def get(self, item_id: str) -> Optional[SwapItem]:
        return await self._repo.get(item_id)

    async def list(self) -> List[SwapItem]:
        return await self._repo.list()

    async def delete(self, item_id: str) -> bool:
        return await self._repo.delete(item_id)
