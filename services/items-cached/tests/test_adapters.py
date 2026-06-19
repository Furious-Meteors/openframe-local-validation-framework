"""
Tests for ItemPostgresRepository and ItemRedisRepository.

Regression tests for Bug 2 (UndefinedTableError translation) and
Bug 3 (NotNullViolationError translation) — both confirmed in live
Docker validation.
"""
from __future__ import annotations

import asyncio
import pytest
import asyncpg

from openframe.core.exceptions import AdapterQueryError, AdapterTimeoutError
from openframe.core.health import HealthCheck
from openframe.core.ports import BaseRepository

from src.domain.item import Item


# ── ItemPostgresRepository ───────────────────────────────────────────────────

def test_pg_adapter_satisfies_base_repository(pg_adapter):
    repo, _ = pg_adapter
    assert isinstance(repo, BaseRepository)


def test_pg_adapter_satisfies_health_check(pg_adapter):
    repo, _ = pg_adapter
    assert isinstance(repo, HealthCheck)


def test_pg_table_is_items(pg_adapter):
    repo, _ = pg_adapter
    assert repo._table == "items"


def test_pg_row_to_entity(pg_adapter):
    repo, _ = pg_adapter
    from unittest.mock import MagicMock
    row = {"id": "1", "name": "W", "description": None,
           "status": "active", "created_at": None}
    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, k: row[k]
    mock_row.get = lambda k, d=None: row.get(k, d)
    item = repo._row_to_entity(mock_row)
    assert isinstance(item, Item)
    assert item.id == "1"
    assert item.status == "active"


def test_pg_entity_to_row_excludes_created_at(pg_adapter, item_factory):
    """
    REGRESSION: confirms created_at is intentionally excluded from the
    row dict — the timestamp is set by the service layer (Bug 3 fix),
    not passed through to the adapter's row mapping.
    """
    repo, _ = pg_adapter
    item = item_factory()
    row = repo._entity_to_row(item)
    assert "created_at" not in row
    assert set(row.keys()) == {"id", "name", "description", "status"}


# REGRESSION: Bug 2 — UndefinedTableError must translate to AdapterQueryError

async def test_pg_undefined_table_raises_adapter_query_error(pg_adapter):
    """
    Regression test for the live-validation scenario where the 'items'
    table didn't exist. Confirms asyncpg.exceptions.UndefinedTableError
    is correctly translated to AdapterQueryError with cause chaining intact.
    The architecture handled this correctly during live validation —
    this test locks in that the translation stays working.
    """
    repo, pool = pg_adapter
    pool.fetchrow.side_effect = asyncpg.exceptions.UndefinedTableError(
        'relation "items" does not exist'
    )
    with pytest.raises(AdapterQueryError) as exc_info:
        await repo.get("any-id")
    assert exc_info.value.__cause__ is not None


# REGRESSION: Bug 3 — NotNullViolationError must translate to AdapterQueryError

async def test_pg_not_null_violation_raises_adapter_query_error(pg_adapter, item_factory):
    """
    Regression test for the live-validation bug where created_at=None
    violated the NOT NULL constraint. Confirms the adapter correctly
    translates NotNullViolationError to AdapterQueryError — the actual
    fix lives in the service layer (test_create_item_sets_created_at_when_missing).
    """
    repo, pool = pg_adapter
    pool.fetchrow.side_effect = asyncpg.exceptions.NotNullViolationError(
        'null value in column "created_at" of relation "items" '
        'violates not-null constraint'
    )
    with pytest.raises(AdapterQueryError) as exc_info:
        await repo.create(item_factory())
    assert exc_info.value.__cause__ is not None


async def test_pg_timeout_raises_adapter_timeout_error(pg_adapter):
    repo, pool = pg_adapter
    pool.fetchrow.side_effect = asyncio.TimeoutError()
    with pytest.raises(AdapterTimeoutError):
        await repo.get("any-id")


# ── ItemRedisRepository ──────────────────────────────────────────────────────

def test_redis_adapter_satisfies_base_repository(redis_adapter):
    repo, _ = redis_adapter
    assert isinstance(repo, BaseRepository)


def test_redis_adapter_satisfies_health_check(redis_adapter):
    repo, _ = redis_adapter
    assert isinstance(repo, HealthCheck)


def test_redis_dict_to_entity(redis_adapter):
    repo, _ = redis_adapter
    data = {"id": "1", "name": "W", "description": None,
            "status": "active", "created_at": None}
    item = repo._dict_to_entity(data)
    assert isinstance(item, Item)
    assert item.id == "1"
    assert item.status == "active"


def test_redis_entity_to_dict_round_trip(redis_adapter, item_factory):
    repo, _ = redis_adapter
    item = item_factory()
    data = repo._entity_to_dict(item)
    assert data["id"] == item.id
    assert data["name"] == item.name
    assert data["status"] == item.status


async def test_redis_get_returns_none_on_miss(redis_adapter):
    repo, client = redis_adapter
    client.get.return_value = None
    result = await repo.get("missing")
    assert result is None
