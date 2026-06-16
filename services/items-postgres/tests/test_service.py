"""
Tests for ItemService.

Service depends only on ItemRepositoryPort — never on concrete adapters.
All repo calls are mocked.
"""
from __future__ import annotations

import pytest

from src.domain.item import Item
from src.application.services.item_service import ItemService


async def test_get_item_returns_item(service, mock_repo, item_factory):
    item = item_factory(id="abc")
    mock_repo.get.return_value = item
    result = await service.get_item("abc")
    assert result == item
    mock_repo.get.assert_called_once_with("abc")


async def test_get_item_returns_none_when_missing(service, mock_repo):
    mock_repo.get.return_value = None
    result = await service.get_item("missing")
    assert result is None


async def test_list_items_returns_items_and_total(service, mock_repo, item_factory):
    items = [item_factory(id="1"), item_factory(id="2")]
    mock_repo.list.return_value = (items, 2)
    result_items, total = await service.list_items(limit=10, offset=0)
    assert len(result_items) == 2
    assert total == 2
    mock_repo.list.assert_called_once_with(limit=10, offset=0)


async def test_create_item_calls_repo(service, mock_repo, item_factory):
    item = item_factory()
    mock_repo.create.return_value = item
    result = await service.create_item(item)
    assert result == item
    mock_repo.create.assert_called_once_with(item)


async def test_create_item_generates_id_when_empty(service, mock_repo):
    """Service generates UUID when item.id is empty string."""
    item = Item(id="", name="Widget")
    mock_repo.create.return_value = item
    await service.create_item(item)
    call_arg = mock_repo.create.call_args[0][0]
    assert call_arg.id != ""


async def test_update_item_returns_updated(service, mock_repo, item_factory):
    item = item_factory(id="abc")
    mock_repo.update.return_value = item
    result = await service.update_item(item)
    assert result == item


async def test_update_item_returns_none_when_missing(service, mock_repo, item_factory):
    mock_repo.update.return_value = None
    result = await service.update_item(item_factory())
    assert result is None


async def test_delete_item_returns_true(service, mock_repo):
    mock_repo.delete.return_value = True
    result = await service.delete_item("abc")
    assert result is True


async def test_delete_item_returns_false_when_missing(service, mock_repo):
    mock_repo.delete.return_value = False
    result = await service.delete_item("missing")
    assert result is False


async def test_filter_by_status_delegates_to_repo(service, mock_repo, item_factory):
    items = [item_factory(status="inactive")]
    mock_repo.find_by_status.return_value = items
    result = await service.filter_by_status("inactive")
    assert result == items
    mock_repo.find_by_status.assert_called_once_with("inactive")


async def test_bulk_import_delegates_to_repo(service, mock_repo, item_factory):
    items = [item_factory(id="1"), item_factory(id="2")]
    mock_repo.bulk_import.return_value = 2
    count = await service.bulk_import(items)
    assert count == 2
    mock_repo.bulk_import.assert_called_once_with(items)


async def test_health_returns_ping_and_ready(service, mock_repo):
    mock_repo.ping.return_value = True
    mock_repo.is_ready.return_value = True
    result = await service.health()
    assert result == {"ping": True, "is_ready": True}


async def test_service_no_adapter_imports():
    """Service must not import from openframe.adapters or asyncpg."""
    import ast
    import inspect
    import src.application.services.item_service as svc_module
    source = inspect.getsource(svc_module)
    assert "openframe.adapters" not in source
    # Use AST to check actual imports, not mentions in comments/docstrings
    tree = ast.parse(source)
    all_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            all_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            all_imports.append(node.module)
    assert not any("asyncpg" in i for i in all_imports), \
        "service imports asyncpg — must be infrastructure-free"
    assert not any("PostgresRepository" in i for i in all_imports)
