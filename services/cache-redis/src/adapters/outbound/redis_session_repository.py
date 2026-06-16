from datetime import datetime, timezone
from typing import Any, Dict, Optional

from redis.asyncio import Redis

from domain.session import Session


class RedisSessionRepository:
    def __init__(self, client: Redis, prefix: str) -> None:
        self._r = client
        self._prefix = prefix

    def _key(self, session_id: str) -> str:
        return f"{self._prefix}:session:{session_id}"

    async def save(self, session: Session, ttl: int) -> None:
        if session.created_at is None:
            session = session.model_copy(
                update={"created_at": datetime.now(timezone.utc)}
            )
        key = self._key(session.id)
        async with self._r.pipeline() as pipe:
            await pipe.set(key, session.model_dump_json())
            await pipe.expire(key, ttl)
            await pipe.execute()

    async def get(self, session_id: str) -> Optional[Session]:
        raw = await self._r.get(self._key(session_id))
        if raw is None:
            return None
        return Session.model_validate_json(raw)

    async def extend(self, session_id: str, seconds: int) -> bool:
        result = await self._r.expire(self._key(session_id), seconds)
        return bool(result)

    async def delete(self, session_id: str) -> bool:
        result = await self._r.delete(self._key(session_id))
        return result > 0

    async def stats(self) -> Dict[str, Any]:
        info = await self._r.info()
        return {
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "total_commands_processed": info.get("total_commands_processed"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }
