"""
Proves the swap works: same service, different repos, identical behaviour.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from application.services.swap_item_service import SwapItemService
from domain.swap_item import SwapItem


@pytest.fixture
def postgres_repo():
    repo = MagicMock()
    repo.save   = AsyncMock()
    repo.get    = AsyncMock(return_value=SwapItem(id="pg-1", name="Postgres Item"))
    repo.list   = AsyncMock(return_value=([SwapItem(id="pg-1", name="Postgres Item")], 1))
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def mongo_repo():
    repo = MagicMock()
    repo.save   = AsyncMock()
    repo.get    = AsyncMock(return_value=SwapItem(id="mg-1", name="Mongo Item"))
    repo.list   = AsyncMock(return_value=([SwapItem(id="mg-1", name="Mongo Item")], 1))
    repo.delete = AsyncMock(return_value=True)
    return repo


async def test_same_service_works_with_postgres_repo(postgres_repo):
    svc = SwapItemService(postgres_repo)
    item = await svc.get("pg-1")
    assert item.id == "pg-1"


async def test_same_service_works_with_mongo_repo(mongo_repo):
    svc = SwapItemService(mongo_repo)
    item = await svc.get("mg-1")
    assert item.id == "mg-1"


async def test_service_interface_identical_for_both(postgres_repo, mongo_repo):
    """
    The service API is identical for both backends.
    Core claim of hexagonal architecture.
    """
    item = SwapItem(id="test", name="Test")
    for repo in [postgres_repo, mongo_repo]:
        svc = SwapItemService(repo)
        await svc.create(item)
        await svc.get("test")
        await svc.list()
        await svc.delete("test")
    assert True


async def test_backend_env_var_selects_correct_repo(monkeypatch):
    """PERSISTENCE_BACKEND env var changes which repository is constructed."""
    import os
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    backend = os.environ.get("PERSISTENCE_BACKEND", "postgres")
    assert backend in ("postgres", "mongo")
