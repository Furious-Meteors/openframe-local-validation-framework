from __future__ import annotations

import pytest
from openframe.core.ports import BaseRepository, Lifecycle

from src.adapters.outbound.session_repository import SessionRedisRepository
from src.domain.session import Session


def test_adapter_satisfies_base_repository(adapter):
    repo, _, _ = adapter
    assert isinstance(repo, BaseRepository)


def test_adapter_satisfies_health_check(adapter):
    repo, _, _ = adapter
    assert isinstance(repo, Lifecycle)


def test_dict_to_entity(adapter, session_factory):
    repo, _, _ = adapter
    data = {"id": "s1", "user_id": "u1", "created_at": None,
            "expires_at": None, "metadata": {}}
    session = repo._dict_to_entity(data)
    assert isinstance(session, Session)
    assert session.id == "s1"
    assert session.user_id == "u1"


def test_entity_to_dict(adapter, session_factory):
    repo, _, _ = adapter
    session = session_factory()
    data = repo._entity_to_dict(session)
    assert data["id"] == "sess-1"
    assert data["user_id"] == "user-123"


def test_make_key_uses_prefix(adapter):
    repo, _, _ = adapter
    key = repo._make_key("sess-1")
    assert "sess-1" in key


# ── Niche feature: extend_ttl (EXPIRE command) ────────────────────────────

async def test_extend_ttl_calls_expire(adapter):
    repo, client, _ = adapter
    client.expire.return_value = 1
    result = await repo.extend_ttl("sess-1", 3600)
    assert result is True
    client.expire.assert_called_once()
    call_args = client.expire.call_args[0]
    assert "sess-1" in call_args[0]
    assert call_args[1] == 3600


async def test_extend_ttl_returns_false_when_key_missing(adapter):
    repo, client, _ = adapter
    client.expire.return_value = 0
    result = await repo.extend_ttl("missing", 3600)
    assert result is False


# ── Niche feature: get_stats (PIPELINE) ───────────────────────────────────

async def test_get_stats_uses_pipeline(adapter):
    repo, client, pipe = adapter
    pipe.execute.return_value = [
        5,
        {"connected_clients": 2, "total_commands_processed": 50},
        {"used_memory_human": "2M"},
    ]
    result = await repo.get_stats()
    assert "session_count" in result
    assert "total_keys" in result
    client.pipeline.assert_called_once()
