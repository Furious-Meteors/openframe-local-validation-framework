"""
Composition root — Stage 2 wiring.

TWO adapters → PluginRegistry.

This is the canonical upgrade from Stage 1 (items-postgres/bootstrap/dependencies.py):
  - lru_cache replaced with PluginRegistry
  - Two plugins registered: Postgres (persistence) + Redis (cache)
  - Startup ordering: Postgres first, Redis second
  - Shutdown ordering: Redis first, Postgres second (LIFO)
  - initialise() called in FastAPI lifespan
  - shutdown() called in FastAPI lifespan cleanup

The service layer (ItemCachedService) is injected with two repositories
looked up from the registry by capability string.

Capability taxonomy:
    "persistence" → PostgresPlugin → ItemPostgresRepository
    "cache"       → RedisPlugin   → ItemRedisRepository
"""
from __future__ import annotations

from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
from openframe.adapters.db.redis    import RedisPlugin, RedisSettings
from openframe.core.plugins         import PluginRegistry
from openframe.core.tracing         import TracingProxy

from src.adapters.outbound.item_postgres_repository import ItemPostgresRepository
from src.adapters.outbound.item_redis_repository    import ItemRedisRepository
from src.application.services.item_service          import ItemCachedService

# Module-level registry — initialised once in lifespan
_registry: PluginRegistry | None = None


async def initialise() -> None:
    """
    Register and initialise both plugins.

    Called once in FastAPI lifespan on startup.
    Registration order = initialisation order.
    Postgres first (persistence), Redis second (cache).

    If either plugin fails to initialise, initialize_all() raises
    AdapterConnectionError and the app enters degraded mode.
    """
    global _registry
    _registry = PluginRegistry()

    # Postgres first — items must be persisted before caching
    _registry.register(PostgresPlugin(PostgresSettings(), table="items", id_column="id"))

    # Redis second — cache layer depends on persistence being available
    _registry.register(RedisPlugin(RedisSettings()))

    # Initialise all — raises AdapterConnectionError if any backend is down
    await _registry.initialize_all()


async def shutdown() -> None:
    """
    Shut down all plugins in reverse order (LIFO).

    Redis shuts down first, Postgres second.
    Never raises — logs errors and continues.
    """
    if _registry is not None:
        await _registry.shutdown_all()


async def health_all() -> dict:
    """Aggregate health across all plugins."""
    if _registry is None:
        return {"status": "not_initialised"}
    return await _registry.health_all()


def get_item_service() -> ItemCachedService:
    """
    FastAPI dependency — injected via Depends(get_item_service).

    Looks up plugins by capability string.
    Wraps each repository with TracingProxy for automatic OTel spans.

    Span prefixes:
        repository.item.postgres — Postgres spans
        cache.item.redis         — Redis spans
    """
    if _registry is None:
        raise RuntimeError(
            "PluginRegistry not initialised. "
            "Call await initialise() in FastAPI lifespan first."
        )

    persistence = TracingProxy(
        _registry.get("persistence").get_repository(),
        prefix="repository.item.postgres",
    )
    cache = TracingProxy(
        _registry.get("cache").get_repository(),
        prefix="cache.item.redis",
    )

    return ItemCachedService(persistence=persistence, cache=cache)
