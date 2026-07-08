"""
Shared fixtures for items-cached tests.

OTel reset provided by openframe.core.testing.fixtures.
The autouse _test_env fixture sets required env vars so TestClient(app)
never raises pydantic ValidationError during lifespan.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from openframe.core.ports import PluginHealth, PluginStatus
from openframe.core.testing.fixtures import *  # noqa: F401, F403

from src.domain.item import Item


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def item_factory():
    def _make(
        id: str = "cached-1",
        name: str = "Cached Widget",
        description: str | None = None,
        status: str = "active",
    ) -> Item:
        return Item(id=id, name=name, description=description, status=status)
    return _make


@pytest.fixture
def mock_persistence():
    """Mocked ItemRepositoryPort — represents Postgres."""
    repo = MagicMock()
    repo.get      = AsyncMock(return_value=None)
    repo.list     = AsyncMock(return_value=([], 0))
    repo.create   = AsyncMock()
    repo.update   = AsyncMock(return_value=None)
    repo.delete   = AsyncMock(return_value=False)
    repo.health   = AsyncMock(return_value=PluginHealth(status=PluginStatus.READY))
    return repo


@pytest.fixture
def mock_cache():
    """Mocked ItemRepositoryPort — represents Redis."""
    repo = MagicMock()
    repo.get      = AsyncMock(return_value=None)
    repo.list     = AsyncMock(return_value=([], 0))
    repo.create   = AsyncMock()
    repo.update   = AsyncMock(return_value=None)
    repo.delete   = AsyncMock(return_value=False)
    repo.health   = AsyncMock(return_value=PluginHealth(status=PluginStatus.READY))
    return repo


@pytest.fixture
def service(mock_persistence, mock_cache):
    from src.application.services.item_service import ItemCachedService
    return ItemCachedService(persistence=mock_persistence, cache=mock_cache)


# ── Postgres adapter fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_pg_pool():
    pool = MagicMock()
    pool.fetch    = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.execute  = AsyncMock(return_value="DELETE 0")
    return pool


@pytest.fixture
def pg_settings():
    from openframe.adapters.db.postgres import PostgresSettings
    return PostgresSettings(database_url="postgresql://test:test@localhost/test")


@pytest.fixture
def pg_adapter(pg_settings, mock_pg_pool):
    import openframe.adapters.db.postgres.connection as conn_module
    conn_module._pool_cache[pg_settings.database_url] = mock_pg_pool
    from src.adapters.outbound.item_postgres_repository import ItemPostgresRepository
    r = ItemPostgresRepository(pg_settings)
    yield r, mock_pg_pool
    conn_module._pool_cache.clear()


# ── Redis adapter fixtures ───────────────────────────────────────────────────

@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    client.get    = AsyncMock(return_value=None)
    client.set    = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.ping   = AsyncMock(return_value=True)
    client.info   = AsyncMock(return_value={"redis_version": "7.0.0"})

    async def _scan_iter(match=None, count=None):
        return
        yield
    client.scan_iter = _scan_iter
    return client


@pytest.fixture
def redis_settings():
    from openframe.adapters.db.redis import RedisSettings
    return RedisSettings(redis_url="redis://localhost:6379/0")


@pytest.fixture
def redis_adapter(redis_settings, mock_redis_client):
    import openframe.adapters.db.redis.connection as conn_module
    conn_module._client_cache[redis_settings.redis_url] = mock_redis_client
    from src.adapters.outbound.item_redis_repository import ItemRedisRepository
    r = ItemRedisRepository(redis_settings)
    yield r, mock_redis_client
    conn_module._client_cache.clear()
