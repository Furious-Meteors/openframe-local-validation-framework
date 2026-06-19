"""
Redis adapter for item caching.

Stores items as JSON under keys: cached-items:{item_id}
TTL controlled by REDIS_DEFAULT_TTL (default: 300 seconds).

This adapter acts as the cache layer alongside Postgres.
"""
from __future__ import annotations

from typing import Any

from openframe.adapters.db.redis import RedisRepository
from src.domain.item import Item


class ItemRedisRepository(RedisRepository[Item]):
    """Item cache repository backed by Redis."""

    def _dict_to_entity(self, data: dict[str, Any]) -> Item:
        return Item(**data)

    def _entity_to_dict(self, entity: Item) -> dict[str, Any]:
        return entity.model_dump(mode="json")
