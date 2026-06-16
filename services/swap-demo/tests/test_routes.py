from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from domain.swap_item import SwapItem
from entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.create = AsyncMock()
    svc.get    = AsyncMock(return_value=None)
    svc.list   = AsyncMock(return_value=[])
    svc.delete = AsyncMock(return_value=False)
    return svc


@pytest.fixture
def client(mock_service):
    from bootstrap.dependencies import get_swap_item_service
    app.dependency_overrides[get_swap_item_service] = lambda: mock_service
    with patch("bootstrap.dependencies.init_backends", return_value=None):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, mock_service
    app.dependency_overrides.clear()


def test_info_returns_active_backend(client):
    c, _ = client
    resp = c.get("/info")
    assert resp.status_code == 200
    assert "persistence_backend" in resp.json()


def test_create_returns_201(client):
    c, svc = client
    item = SwapItem(id="swap-1", name="Test")
    svc.create.return_value = item
    resp = c.post("/items", json={"id": "swap-1", "name": "Test"})
    assert resp.status_code == 201


def test_get_returns_200(client):
    c, svc = client
    svc.get.return_value = SwapItem(id="swap-1", name="Test")
    resp = c.get("/items/swap-1")
    assert resp.status_code == 200


def test_get_returns_404(client):
    c, svc = client
    svc.get.return_value = None
    resp = c.get("/items/missing")
    assert resp.status_code == 404


def test_delete_returns_204(client):
    c, svc = client
    svc.delete.return_value = True
    resp = c.delete("/items/swap-1")
    assert resp.status_code == 204


def test_delete_returns_404(client):
    c, svc = client
    svc.delete.return_value = False
    resp = c.delete("/items/missing")
    assert resp.status_code == 404
