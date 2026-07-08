from __future__ import annotations

import pytest
from domain.swap_item import SwapItem


async def test_create_calls_save(service, mock_repo, item_factory):
    item = item_factory()
    mock_repo.save.return_value = None
    result = await service.create(item)
    assert result == item
    mock_repo.save.assert_called_once_with(item)


async def test_get_returns_item(service, mock_repo, item_factory):
    item = item_factory()
    mock_repo.get.return_value = item
    result = await service.get("swap-1")
    assert result == item


async def test_get_returns_none(service, mock_repo):
    mock_repo.get.return_value = None
    result = await service.get("missing")
    assert result is None


async def test_list_returns_items(service, mock_repo, item_factory):
    items = [item_factory(id="1"), item_factory(id="2")]
    mock_repo.list.return_value = (items, len(items))
    result = await service.list()
    assert len(result) == 2


async def test_delete_returns_true(service, mock_repo):
    mock_repo.delete.return_value = True
    result = await service.delete("swap-1")
    assert result is True


async def test_delete_returns_false(service, mock_repo):
    mock_repo.delete.return_value = False
    result = await service.delete("missing")
    assert result is False
