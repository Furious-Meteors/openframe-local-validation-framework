"""
Tests for ItemCachedService — the cache-aside orchestration logic.

Includes the explicit regression test for Bug 3 (created_at not set
before create()) discovered during live Docker validation.
"""
from __future__ import annotations

import pytest
from openframe.core.ports import PluginHealth, PluginStatus

from src.domain.item import Item


# ── REGRESSION: Bug 3 — created_at must be set before persistence.create() ──

async def test_create_item_sets_created_at_when_missing(
    service, mock_persistence, item_factory
):
    """
    Regression test for the live-validation bug where create_item()
    passed created_at=None straight through to Postgres, violating
    the NOT NULL constraint (NotNullViolationError → AdapterQueryError).
    """
    item = item_factory()
    assert item.created_at is None  # precondition
    mock_persistence.create.return_value = item
    await service.create_item(item)
    created_arg = mock_persistence.create.call_args[0][0]
    assert created_arg.created_at is not None


async def test_create_item_preserves_existing_created_at(
    service, mock_persistence, item_factory
):
    """If created_at is already set, create_item() must not overwrite it."""
    from datetime import datetime, timezone
    fixed_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    item = item_factory().model_copy(update={"created_at": fixed_time})
    mock_persistence.create.return_value = item
    await service.create_item(item)
    created_arg = mock_persistence.create.call_args[0][0]
    assert created_arg.created_at == fixed_time


# ── get_item() — cache-aside read path ──────────────────────────────────────

async def test_get_item_returns_cache_hit_without_touching_persistence(
    service, mock_persistence, mock_cache, item_factory
):
    cached = item_factory()
    mock_cache.get.return_value = cached
    result = await service.get_item("cached-1")
    assert result == cached
    mock_persistence.get.assert_not_called()


async def test_get_item_falls_back_to_persistence_on_cache_miss(
    service, mock_persistence, mock_cache, item_factory
):
    mock_cache.get.return_value = None
    item = item_factory()
    mock_persistence.get.return_value = item
    result = await service.get_item("cached-1")
    assert result == item
    mock_persistence.get.assert_called_once_with("cached-1")


async def test_get_item_populates_cache_after_persistence_read(
    service, mock_persistence, mock_cache, item_factory
):
    mock_cache.get.return_value = None
    item = item_factory()
    mock_persistence.get.return_value = item
    await service.get_item("cached-1")
    mock_cache.create.assert_called_once_with(item)


async def test_get_item_returns_none_when_missing_everywhere(
    service, mock_persistence, mock_cache
):
    mock_cache.get.return_value = None
    mock_persistence.get.return_value = None
    result = await service.get_item("missing")
    assert result is None


async def test_get_item_does_not_populate_cache_when_persistence_misses(
    service, mock_persistence, mock_cache
):
    mock_cache.get.return_value = None
    mock_persistence.get.return_value = None
    await service.get_item("missing")
    mock_cache.create.assert_not_called()


# ── Graceful degradation — Redis failures never break reads/writes ──────────

async def test_get_item_falls_through_to_persistence_when_cache_read_raises(
    service, mock_persistence, mock_cache, item_factory
):
    mock_cache.get.side_effect = Exception("Redis connection lost")
    item = item_factory()
    mock_persistence.get.return_value = item
    result = await service.get_item("cached-1")  # must not raise
    assert result == item


async def test_get_item_succeeds_when_cache_populate_fails(
    service, mock_persistence, mock_cache, item_factory
):
    mock_cache.get.return_value = None
    item = item_factory()
    mock_persistence.get.return_value = item
    mock_cache.create.side_effect = Exception("Redis down")
    result = await service.get_item("cached-1")  # must not raise
    assert result == item


async def test_create_item_succeeds_when_cache_populate_fails(
    service, mock_persistence, mock_cache, item_factory
):
    item = item_factory()
    mock_persistence.create.return_value = item
    mock_cache.create.side_effect = Exception("Redis down")
    result = await service.create_item(item)  # must not raise
    assert result is not None


# ── update_item() — write-through with cache invalidation ───────────────────

async def test_update_item_invalidates_cache_on_success(
    service, mock_persistence, mock_cache, item_factory
):
    item = item_factory()
    mock_persistence.update.return_value = item
    await service.update_item(item)
    mock_cache.delete.assert_called_once_with(item.id)


async def test_update_item_returns_none_when_persistence_misses(
    service, mock_persistence, mock_cache
):
    mock_persistence.update.return_value = None
    result = await service.update_item(Item(id="missing", name="X"))
    assert result is None


async def test_update_item_does_not_invalidate_cache_when_missing(
    service, mock_persistence, mock_cache
):
    mock_persistence.update.return_value = None
    await service.update_item(Item(id="missing", name="X"))
    mock_cache.delete.assert_not_called()


async def test_update_item_succeeds_when_cache_invalidation_fails(
    service, mock_persistence, mock_cache, item_factory
):
    item = item_factory()
    mock_persistence.update.return_value = item
    mock_cache.delete.side_effect = Exception("Redis down")
    result = await service.update_item(item)  # must not raise
    assert result == item


# ── delete_item() — write-through with cache invalidation ───────────────────

async def test_delete_item_invalidates_cache_on_success(
    service, mock_persistence, mock_cache
):
    mock_persistence.delete.return_value = True
    await service.delete_item("cached-1")
    mock_cache.delete.assert_called_once_with("cached-1")


async def test_delete_item_returns_false_when_persistence_misses(
    service, mock_persistence, mock_cache
):
    mock_persistence.delete.return_value = False
    result = await service.delete_item("missing")
    assert result is False
    mock_cache.delete.assert_not_called()


async def test_delete_item_succeeds_when_cache_invalidation_fails(
    service, mock_persistence, mock_cache
):
    mock_persistence.delete.return_value = True
    mock_cache.delete.side_effect = Exception("Redis down")
    result = await service.delete_item("cached-1")  # must not raise
    assert result is True


# ── list_items() — always Postgres ──────────────────────────────────────────

async def test_list_items_reads_from_persistence_only(
    service, mock_persistence, mock_cache, item_factory
):
    items = [item_factory(id="1"), item_factory(id="2")]
    mock_persistence.list.return_value = (items, 2)
    result_items, total = await service.list_items(limit=10, offset=0)
    assert total == 2
    mock_persistence.list.assert_called_once_with(limit=10, offset=0)
    mock_cache.list.assert_not_called()


# ── health() ────────────────────────────────────────────────────────────────

async def test_health_checks_both_backends(service, mock_persistence, mock_cache):
    mock_persistence.health.return_value = PluginHealth(status=PluginStatus.READY)
    mock_cache.health.return_value       = PluginHealth(status=PluginStatus.READY)
    result = await service.health()
    assert result == {
        "postgres_ping":  True, "postgres_ready": True,
        "redis_ping":     True, "redis_ready":    True,
    }


def test_service_no_adapter_imports():
    import src.application.services.item_service as m, inspect
    source = inspect.getsource(m)
    assert "openframe.adapters" not in source
    assert "asyncpg" not in source
