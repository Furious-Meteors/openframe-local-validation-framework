"""Session application service."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from openframe.core.ports import PluginStatus

from src.application.ports.session_repository import SessionRepositoryPort
from src.domain.session import Session


class SessionService:
    def __init__(self, repository: SessionRepositoryPort) -> None:
        self._repo = repository

    async def create_session(
        self,
        session: Session,
        ttl_seconds: int = 3600,
    ) -> Session:
        now = datetime.now(timezone.utc)
        session = session.model_copy(update={
            "created_at": now,
            "expires_at": now + timedelta(seconds=ttl_seconds),
        })
        return await self._repo.create(session)

    async def get_session(self, session_id: str) -> Session | None:
        return await self._repo.get(session_id)

    async def list_sessions(
        self, limit: int = 20, offset: int = 0,
    ) -> tuple[list[Session], int]:
        return await self._repo.list(limit=limit, offset=offset)

    async def invalidate(self, session_id: str) -> bool:
        return await self._repo.delete(session_id)

    async def extend_session(self, session_id: str, seconds: int) -> bool:
        """
        Extend TTL — uses Redis EXPIRE niche feature in the adapter.
        """
        return await self._repo.extend_ttl(session_id, seconds)

    async def get_stats(self) -> dict:
        """
        Redis server stats — uses PIPELINE niche feature in the adapter.
        """
        return await self._repo.get_stats()

    async def health(self) -> dict:
        health = await self._repo.health()
        ready = health.status == PluginStatus.READY
        return {"ping": ready, "is_ready": ready}
