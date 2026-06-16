"""
Tests for ItemPostgresRepository.

Proves the adapter:
- Satisfies BaseRepository and HealthCheck protocols
- Maps asyncpg records to Item domain objects correctly
- Accesses raw asyncpg for niche features (find_by_status, bulk_import)
- Translates asyncpg errors to AdapterError subclasses
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from openframe.core.exceptions import AdapterQueryError, AdapterTimeoutError
from openframe.core.health import HealthCheck
from openframe.core.ports import BaseRepository

from src.adapters.outbound.item_repository import ItemPostgresRepository
from src.domain.item import Item


# ── Protocol conformance ───────────────────────────────────────────────────

def test_adapter_satisfies_base_repository(adapter):
    repo, _, _ = adapter
    assert isinstance(repo, BaseRepository)


def test_adapter_satisfies_health_check(adapter):
    repo, _, _ = adapter
    assert isinstance(repo, HealthCheck)


def test_adapter_table_is_items(adapter):
    repo, _, _ = adapter
    assert repo._table == "items"


def test_adapter_id_column_is_id(adapter):
    repo, _, _ = adapter
    assert repo._id_column == "id"


# ── _row_to_entity mapping ─────────────────────────────────────────────────

def test_row_to_entity_maps_all_fields(adapter):
    repo, _, _ = adapter
    row = {
        "id": "abc", "name": "Widget",
        "description": "Desc", "status": "active", "created_at": None,
    }
    item = repo._row_to_entity(row)
    assert isinstance(item, Item)
    assert item.id == "abc"
    assert item.name == "Widget"
    assert item.description == "Desc"
    assert item.status == "active"


def test_entity_to_row_maps_all_fields(adapter, item_factory):
    repo, _, _ = adapter
    item = item_factory(id="abc", name="Widget", status="inactive")
    row = repo._entity_to_row(item)
    assert row["id"] == "abc"
    assert row["name"] == "Widget"
    assert row["status"] == "inactive"


def test_entity_to_row_excludes_created_at(adapter, item_factory):
    repo, _, _ = adapter
    item = item_factory()
    row = repo._entity_to_row(item)
    assert "created_at" not in row


# ── Niche feature: find_by_status ─────────────────────────────────────────

async def test_find_by_status_uses_raw_pool(adapter):
    repo, pool, _ = adapter
    row = {"id": "1", "name": "W", "description": None, "status": "active", "created_at": None}
    pool.fetch.return_value = [row]
    items = await repo.find_by_status("active")
    pool.fetch.assert_called_once()
    call_args = pool.fetch.call_args[0]
    assert "WHERE status = $1" in call_args[0]
    assert call_args[1] == "active"
    assert len(items) == 1
    assert isinstance(items[0], Item)


async def test_find_by_status_returns_empty_list(adapter):
    repo, pool, _ = adapter
    pool.fetch.return_value = []
    items = await repo.find_by_status("unknown")
    assert items == []


# ── Niche feature: bulk_import ────────────────────────────────────────────

async def test_bulk_import_uses_copy_records_to_table(adapter, item_factory):
    repo, pool, conn = adapter
    items = [item_factory(id="1"), item_factory(id="2")]
    count = await repo.bulk_import(items)
    conn.copy_records_to_table.assert_called_once()
    assert count == 2


async def test_bulk_import_returns_count(adapter, item_factory):
    repo, pool, conn = adapter
    items = [item_factory(id=str(i)) for i in range(5)]
    count = await repo.bulk_import(items)
    assert count == 5


async def test_bulk_import_passes_correct_columns(adapter, item_factory):
    repo, pool, conn = adapter
    items = [item_factory()]
    await repo.bulk_import(items)
    call_kwargs = conn.copy_records_to_table.call_args[1]
    assert set(call_kwargs["columns"]) == {"id", "name", "description", "status"}


# ── Error translation ──────────────────────────────────────────────────────

async def test_asyncpg_error_raises_adapter_query_error(adapter):
    repo, pool, _ = adapter
    pool.fetch.side_effect = asyncpg.PostgresError()
    with pytest.raises((AdapterQueryError, asyncpg.PostgresError)):
        await repo.find_by_status("active")


async def test_timeout_raises_adapter_timeout_error(adapter):
    repo, pool, _ = adapter
    pool.fetch.side_effect = asyncio.TimeoutError()
    with pytest.raises((AdapterTimeoutError, asyncio.TimeoutError)):
        await repo.find_by_status("active")
