from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from openframe.core.testing.fixtures import *  # noqa: F401, F403

from src.domain.session import Session


@pytest.fixture
def session_factory():
    def _make(id: str = "sess-1", user_id: str = "user-123") -> Session:
        return Session(id=id, user_id=user_id)
    return _make


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get        = AsyncMock(return_value=None)
    repo.list       = AsyncMock(return_value=([], 0))
    repo.create     = AsyncMock()
    repo.update     = AsyncMock(return_value=None)
    repo.delete     = AsyncMock(return_value=False)
    repo.extend_ttl = AsyncMock(return_value=False)
    repo.get_stats  = AsyncMock(return_value={})
    repo.ping       = AsyncMock(return_value=True)
    repo.is_ready   = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def service(mock_repo):
    from src.application.services.session_service import SessionService
    return SessionService(mock_repo)


@pytest.fixture
def mock_redis():
    client = MagicMock()
    client.get    = AsyncMock(return_value=None)
    client.set    = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.expire = AsyncMock(return_value=1)
    client.mget   = AsyncMock(return_value=[])
    client.ping   = AsyncMock(return_value=True)
    client.info   = AsyncMock(return_value={
        "redis_version": "7.0.0",
        "connected_clients": 1,
        "total_commands_processed": 100,
        "used_memory_human": "1.5M",
    })
    client.dbsize = AsyncMock(return_value=0)

    async def _scan_iter(match=None, count=None):
        return
        yield

    client.scan_iter = _scan_iter

    pipe = AsyncMock()
    pipe.dbsize  = MagicMock()
    pipe.info    = MagicMock()
    pipe.execute = AsyncMock(return_value=[0, {}, {}])
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__  = AsyncMock(return_value=None)
    client.pipeline = MagicMock(return_value=pipe)

    return client, pipe


@pytest.fixture
def mock_settings():
    from openframe.adapters.db.redis import RedisSettings
    return RedisSettings(redis_url="redis://localhost:6379/0")


@pytest.fixture
def adapter(mock_settings, mock_redis):
    client, pipe = mock_redis
    import openframe.adapters.db.redis.connection as conn_module
    conn_module._client_cache[mock_settings.redis_url] = client
    from src.adapters.outbound.session_repository import SessionRedisRepository
    repo = SessionRedisRepository(mock_settings)
    yield repo, client, pipe
    conn_module._client_cache.clear()
