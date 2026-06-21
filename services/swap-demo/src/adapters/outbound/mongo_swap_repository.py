"""
MongoDB adapter for swap-demo persistence.

Extends MongoRepository[SwapItem] from openframe-adapters-db-mongo.
Inherits full CRUD (get, list, create, update, delete, ping, is_ready).
Adds save() — an UPSERT operation not in BaseRepository — using the
inherited _get_collection() helper, following the same pattern as
artifacts-mongo's filter_by_tags() and search() custom operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from openframe.adapters.db.mongo import MongoRepository

from domain.swap_item import SwapItem


class MongoSwapRepository(MongoRepository[SwapItem]):
    _collection = "swap_items"

    def _doc_to_entity(self, doc: dict[str, Any]) -> SwapItem:
        return SwapItem(
            id=doc.get("id") or str(doc.get("_id", "")),
            name=doc["name"],
            description=doc.get("description"),
            created_at=doc.get("created_at"),
        )

    def _entity_to_doc(self, entity: SwapItem) -> dict[str, Any]:
        return {
            "_id":         entity.id,
            "id":          entity.id,
            "name":        entity.name,
            "description": entity.description,
            "created_at":  entity.created_at or datetime.now(timezone.utc),
        }

    async def save(self, item: SwapItem) -> None:
        """
        Upsert — replace or insert by _id.

        Domain-specific operation not in BaseRepository.
        Uses _get_collection() — the same protected helper used by
        artifacts-mongo for its custom filter_by_tags() and search().
        """
        col = self._get_collection()
        doc = self._entity_to_doc(item)
        await col.replace_one({"_id": doc["_id"]}, doc, upsert=True)
