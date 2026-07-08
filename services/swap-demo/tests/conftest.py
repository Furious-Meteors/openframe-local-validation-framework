from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from openframe.core.testing.fixtures import *  # noqa: F401, F403


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("MONGO_URL", "mongodb://test:test@localhost:27017")
    monkeypatch.setenv("MONGO_DATABASE", "test")

from domain.swap_item import SwapItem


@pytest.fixture
def item_factory():
    def _make(id: str = "swap-1", name: str = "Swap Item") -> SwapItem:
        return SwapItem(id=id, name=name)
    return _make


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.save   = AsyncMock()
    repo.get    = AsyncMock(return_value=None)
    repo.list   = AsyncMock(return_value=([], 0))
    repo.delete = AsyncMock(return_value=False)
    return repo


@pytest.fixture
def service(mock_repo):
    from application.services.swap_item_service import SwapItemService
    return SwapItemService(mock_repo)
