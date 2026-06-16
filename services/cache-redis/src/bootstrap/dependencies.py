"""
Composition root — Stage 1 wiring.

One adapter (Redis) → lru_cache direct.

Note: RedisPlugin.capability = "cache" not "persistence".
Redis is the cache layer. When combined with Postgres in Phase 2,
the PluginRegistry distinguishes them by capability string.
"""
from __future__ import annotations

from functools import lru_cache

from openframe.adapters.db.redis import RedisSettings
from openframe.core.tracing import TracingProxy

from src.adapters.outbound.session_repository import SessionRedisRepository
from src.application.services.session_service import SessionService


@lru_cache(maxsize=1)
def _get_settings() -> RedisSettings:
    return RedisSettings()


@lru_cache(maxsize=1)
def _get_repository() -> SessionRedisRepository:
    return SessionRedisRepository(_get_settings())


def get_session_service() -> SessionService:
    traced = TracingProxy(_get_repository(), prefix="cache.session")
    return SessionService(traced)
