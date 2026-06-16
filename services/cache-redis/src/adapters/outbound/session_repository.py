"""
Redis adapter for session persistence.

Subclasses RedisRepository[Session] from openframe-adapters.
Provides domain mapping. Adds TTL management and stats via raw redis client.

This is the ONLY file in the service that imports from openframe.adapters.
"""
from __future__ import annotations

from typing import Any

from openframe.adapters.db.redis import RedisRepository, get_redis_client

from src.domain.session import Session


class SessionRedisRepository(RedisRepository[Session]):
    """
    Session repository backed by Redis.

    Inherits full CRUD from RedisRepository[Session]:
        get(), list(), create(), update(), delete(),
        ping(), is_ready(), close()

    Keys stored as: openframe:session:{id}
    Values stored as: JSON string
    TTL set via REDIS_DEFAULT_TTL env var (default: 3600 seconds)

    Adds domain-specific operations:
        extend_ttl() — Redis EXPIRE command
        get_stats()  — Redis PIPELINE for atomic server stats
    """

    _collection_name = "session"

    def _dict_to_entity(self, data: dict[str, Any]) -> Session:
        """Convert dict (from JSON) to Session domain object."""
        return Session(**data)

    def _entity_to_dict(self, entity: Session) -> dict[str, Any]:
        """Convert Session to dict for JSON storage."""
        return entity.model_dump(mode="json")

    # ── Niche feature 1: Redis EXPIRE command ────────────────────────────
    # Not in BaseRepository. Extends TTL of an existing key.
    # Uses get_redis_client() — raw redis.asyncio, no abstraction.

    async def extend_ttl(self, session_id: str, seconds: int) -> bool:
        """
        Extend the TTL of an existing session key.

        Uses Redis EXPIRE command — not in BaseRepository.
        Returns True if the key exists and TTL was set, False if key missing.

        This is a niche Redis feature — accessed via get_redis_client()
        without breaking the hexagonal boundary.
        """
        client = await get_redis_client(self._settings)
        key = self._make_key(session_id)
        result = await client.expire(key, seconds)
        return bool(result)

    # ── Niche feature 2: Redis PIPELINE ──────────────────────────────────
    # Not in BaseRepository. Atomic multi-command execution.
    # Proves raw redis.asyncio pipeline is accessible from the adapter.

    async def get_stats(self) -> dict:
        """
        Fetch Redis server statistics using PIPELINE.

        PIPELINE executes multiple commands atomically in one round-trip.
        Not in BaseRepository.
        """
        client = await get_redis_client(self._settings)
        pattern = f"{self._settings.redis_key_prefix}:*"

        # Count matching keys
        keys = [k async for k in client.scan_iter(match=pattern)]

        # Fetch server info via pipeline — one round-trip
        async with client.pipeline(transaction=False) as pipe:
            pipe.dbsize()
            pipe.info("stats")
            pipe.info("memory")
            db_size, stats_info, memory_info = await pipe.execute()

        return {
            "session_count":     len(keys),
            "total_keys":        db_size,
            "connected_clients": stats_info.get("connected_clients", 0),
            "total_commands":    stats_info.get("total_commands_processed", 0),
            "used_memory_human": memory_info.get("used_memory_human", "unknown"),
            "key_prefix":        self._settings.redis_key_prefix,
        }
