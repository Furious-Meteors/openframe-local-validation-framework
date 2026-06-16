from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.session import Session
from src.entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.create_session = AsyncMock()
    svc.get_session    = AsyncMock(return_value=None)
    svc.list_sessions  = AsyncMock(return_value=([], 0))
    svc.invalidate     = AsyncMock(return_value=False)
    svc.extend_session = AsyncMock(return_value=False)
    svc.get_stats      = AsyncMock(return_value={})
    svc.health         = AsyncMock(return_value={"ping": True, "is_ready": True})
    return svc


@pytest.fixture
def client(mock_service, monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from src.bootstrap.dependencies import _get_settings, _get_repository, get_session_service
    _get_settings.cache_clear()
    _get_repository.cache_clear()
    app.dependency_overrides[get_session_service] = lambda: mock_service
    with patch("src.entrypoints.http.main.get_session_service", return_value=mock_service):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_service
    app.dependency_overrides.clear()
    _get_settings.cache_clear()
    _get_repository.cache_clear()


def test_health_returns_200(client):
    c, _ = client
    assert c.get("/health").status_code == 200


def test_create_session_returns_201(client):
    c, svc = client
    session = Session(id="s1", user_id="u1")
    svc.create_session.return_value = session
    resp = c.post("/sessions", json={"id": "s1", "user_id": "u1"})
    assert resp.status_code == 201


def test_get_session_returns_200(client):
    c, svc = client
    svc.get_session.return_value = Session(id="s1", user_id="u1")
    resp = c.get("/sessions/s1")
    assert resp.status_code == 200


def test_get_session_returns_404(client):
    c, svc = client
    svc.get_session.return_value = None
    resp = c.get("/sessions/missing")
    assert resp.status_code == 404


def test_extend_ttl_returns_200(client):
    c, svc = client
    svc.extend_session.return_value = True
    resp = c.put("/sessions/s1/extend", json={"seconds": 3600})
    assert resp.status_code == 200


def test_extend_ttl_returns_404_when_missing(client):
    c, svc = client
    svc.extend_session.return_value = False
    resp = c.put("/sessions/missing/extend", json={"seconds": 3600})
    assert resp.status_code == 404


def test_stats_returns_200(client):
    c, svc = client
    svc.get_stats.return_value = {"session_count": 3}
    resp = c.get("/sessions/stats")
    assert resp.status_code == 200


def test_delete_session_returns_204(client):
    c, svc = client
    svc.invalidate.return_value = True
    resp = c.delete("/sessions/s1")
    assert resp.status_code == 204


def test_delete_session_returns_404(client):
    c, svc = client
    svc.invalidate.return_value = False
    resp = c.delete("/sessions/missing")
    assert resp.status_code == 404
