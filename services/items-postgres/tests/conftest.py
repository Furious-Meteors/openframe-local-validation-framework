"""
Shared fixtures for items-postgres tests.

OTel reset provided by openframe.core.testing.fixtures.
All adapter interactions are mocked — zero network calls.

The autouse _test_env fixture sets DATABASE_URL so that PostgresSettings()
(constructed for real inside ItemsPostgresApp.configure() in
test_application_bootstrap.py) doesn't raise ValidationError.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from openframe.core.ports import PluginHealth, PluginStatus
from openframe.core.testing.fixtures import *  # noqa: F401, F403

from src.domain.item import Item


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")


@pytest.fixture
def item_factory():
    """Factory for creating test Item instances."""
    def _make(
        id: str = "test-id",
        name: str = "Test Item",
        description: str | None = "A test item",
        status: str = "active",
    ) -> Item:
        return Item(id=id, name=name, description=description, status=status)
    return _make


@pytest.fixture
def mock_repo():
    """
    A fully mocked ItemRepositoryPort.
    Configure return values per test.
    """
    repo = MagicMock()
    repo.get             = AsyncMock(return_value=None)
    repo.list            = AsyncMock(return_value=([], 0))
    repo.create          = AsyncMock()
    repo.update          = AsyncMock(return_value=None)
    repo.delete          = AsyncMock(return_value=False)
    repo.find_by_status  = AsyncMock(return_value=[])
    repo.bulk_import     = AsyncMock(return_value=0)
    repo.health          = AsyncMock(return_value=PluginHealth(status=PluginStatus.READY))
    return repo


@pytest.fixture
def service(mock_repo):
    """ItemService wired to the mock repository."""
    from src.application.services.item_service import ItemService
    return ItemService(mock_repo)


@pytest.fixture
def mock_pool():
    """A fully mocked asyncpg Pool."""
    pool = MagicMock()
    pool.fetch    = AsyncMock(return_value=[])
    pool.fetchrow = AsyncMock(return_value=None)
    pool.fetchval = AsyncMock(return_value=0)
    pool.execute  = AsyncMock(return_value="DELETE 0")
    conn = AsyncMock()
    conn.copy_records_to_table = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__  = AsyncMock(return_value=None)
    return pool, conn


@pytest.fixture
def mock_settings():
    """PostgresSettings with a fake DATABASE_URL."""
    from openframe.adapters.db.postgres import PostgresSettings
    return PostgresSettings(
        database_url="postgresql://test:test@localhost/test"
    )


@pytest.fixture
def adapter(mock_settings, mock_pool):
    """ItemPostgresRepository wired to a mocked pool."""
    pool, conn = mock_pool
    import openframe.adapters.db.postgres.connection as conn_module
    conn_module._pool_cache[mock_settings.database_url] = pool
    from src.adapters.outbound.item_repository import ItemPostgresRepository
    repo = ItemPostgresRepository(mock_settings)
    yield repo, pool, conn
    conn_module._pool_cache.clear()
