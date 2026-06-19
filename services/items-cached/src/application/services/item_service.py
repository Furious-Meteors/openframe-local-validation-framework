"""
Item service with cache-aside pattern.

Uses two repositories:
    persistence — Postgres (source of truth)
    cache       — Redis (fast read layer, TTL-backed)

The service never imports concrete adapters.
It receives both repositories via constructor injection.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.application.ports.item_repository import ItemRepositoryPort
from src.domain.item import Item

_logger = logging.getLogger(__name__)


class ItemCachedService:
    """
    Item service implementing cache-aside pattern.

    Read flow:
        1. Check Redis cache
        2. On cache miss → read from Postgres, write to Redis
        3. Return result

    Write flow:
        1. Write to Postgres (source of truth)
        2. Invalidate Redis key (delete, not update)
        3. Return result

    If Redis is unavailable, the service degrades gracefully:
        - Reads fall through to Postgres
        - Writes succeed via Postgres only
        - No exception propagates to the caller
    """

    def __init__(
        self,
        persistence: ItemRepositoryPort,  # Postgres
        cache:       ItemRepositoryPort,  # Redis
    ) -> None:
        self._persistence = persistence
        self._cache       = cache

    async def get_item(self, item_id: str) -> Item | None:
        """
        Cache-aside get.

        1. Try Redis first (fast path — sub-millisecond)
        2. On miss — read from Postgres, populate cache
        3. Return item or None
        """
        try:
            cached = await self._cache.get(item_id)
            if cached is not None:
                _logger.debug("Cache HIT: item %s", item_id)
                return cached
        except Exception as exc:
            _logger.warning("Cache read failed (degraded mode): %s", exc)

        _logger.debug("Cache MISS: item %s — reading from Postgres", item_id)
        item = await self._persistence.get(item_id)

        if item is not None:
            try:
                await self._cache.create(item)
            except Exception as exc:
                _logger.warning("Cache write failed (degraded mode): %s", exc)

        return item

    async def list_items(
        self, limit: int = 20, offset: int = 0,
    ) -> tuple[list[Item], int]:
        """List always reads from Postgres — cache is per-entity only."""
        return await self._persistence.list(limit=limit, offset=offset)

    async def create_item(self, item: Item) -> Item:
        """Write to Postgres. Cache populated immediately."""
        if not item.created_at:
            item = item.model_copy(update={"created_at": datetime.now(timezone.utc)})
        created = await self._persistence.create(item)
        try:
            await self._cache.create(created)
        except Exception as exc:
            _logger.warning("Cache populate failed (degraded): %s", exc)
        return created

    async def update_item(self, item: Item) -> Item | None:
        """Update Postgres. Invalidate cache."""
        updated = await self._persistence.update(item)
        if updated is not None:
            try:
                await self._cache.delete(item.id)
            except Exception as exc:
                _logger.warning("Cache invalidation failed (degraded): %s", exc)
        return updated

    async def delete_item(self, item_id: str) -> bool:
        """Delete from Postgres and invalidate cache."""
        deleted = await self._persistence.delete(item_id)
        if deleted:
            try:
                await self._cache.delete(item_id)
            except Exception as exc:
                _logger.warning("Cache invalidation failed (degraded): %s", exc)
        return deleted

    async def health(self) -> dict:
        """Health check across both adapters."""
        return {
            "postgres_ping":  await self._persistence.ping(),
            "postgres_ready": await self._persistence.is_ready(),
            "redis_ping":     await self._cache.ping(),
            "redis_ready":    await self._cache.is_ready(),
        }
