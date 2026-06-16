from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from domain.swap_item import SwapItem


def _to_item(doc: Dict[str, Any]) -> SwapItem:
    doc = dict(doc)
    doc["id"] = doc.pop("_id")
    return SwapItem(**doc)


class MongoSwapRepository:
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        self._col = collection

    async def save(self, item: SwapItem) -> None:
        doc = item.model_dump()
        doc["_id"] = doc.pop("id")
        doc.setdefault("created_at", datetime.now(timezone.utc))
        await self._col.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def get(self, item_id: str) -> Optional[SwapItem]:
        doc = await self._col.find_one({"_id": item_id})
        if doc is None:
            return None
        return _to_item(doc)

    async def list(self) -> List[SwapItem]:
        docs = await self._col.find({}).to_list(length=None)
        return [_to_item(d) for d in docs]

    async def delete(self, item_id: str) -> bool:
        result = await self._col.delete_one({"_id": item_id})
        return result.deleted_count > 0
