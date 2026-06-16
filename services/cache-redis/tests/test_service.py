from __future__ import annotations

import pytest
from src.domain.session import Session


async def test_create_session_sets_created_at(service, mock_repo, session_factory):
    session = session_factory()
    mock_repo.create.return_value = session
    await service.create_session(session)
    created = mock_repo.create.call_args[0][0]
    assert created.created_at is not None


async def test_create_session_sets_expires_at(service, mock_repo, session_factory):
    session = session_factory()
    mock_repo.create.return_value = session
    await service.create_session(session, ttl_seconds=3600)
    created = mock_repo.create.call_args[0][0]
    assert created.expires_at is not None


async def test_get_session_returns_session(service, mock_repo, session_factory):
    session = session_factory()
    mock_repo.get.return_value = session
    result = await service.get_session("sess-1")
    assert result == session


async def test_get_session_returns_none(service, mock_repo):
    mock_repo.get.return_value = None
    result = await service.get_session("missing")
    assert result is None


async def test_invalidate_delegates_to_delete(service, mock_repo):
    mock_repo.delete.return_value = True
    result = await service.invalidate("sess-1")
    assert result is True
    mock_repo.delete.assert_called_once_with("sess-1")


async def test_extend_session_delegates_to_extend_ttl(service, mock_repo):
    mock_repo.extend_ttl.return_value = True
    result = await service.extend_session("sess-1", 7200)
    assert result is True
    mock_repo.extend_ttl.assert_called_once_with("sess-1", 7200)


async def test_extend_session_returns_false_when_missing(service, mock_repo):
    mock_repo.extend_ttl.return_value = False
    result = await service.extend_session("missing", 3600)
    assert result is False


async def test_get_stats_delegates_to_repo(service, mock_repo):
    mock_repo.get_stats.return_value = {"session_count": 5}
    result = await service.get_stats()
    assert result["session_count"] == 5


async def test_health_returns_ping_and_ready(service, mock_repo):
    mock_repo.ping.return_value = True
    mock_repo.is_ready.return_value = True
    result = await service.health()
    assert result == {"ping": True, "is_ready": True}
