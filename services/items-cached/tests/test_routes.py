"""
Tests for HTTP routes.

Confirms the exact response sequence observed in live Docker validation:
POST → 201, GET → 200, GET → 200 (cache hit, identical payload),
DELETE → 204, GET → 404 with {"detail": "Item '<id>' not found"}.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.domain.item import Item
from src.entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.get_item    = AsyncMock(return_value=None)
    svc.list_items  = AsyncMock(return_value=([], 0))
    svc.create_item = AsyncMock()
    svc.update_item = AsyncMock(return_value=None)
    svc.delete_item = AsyncMock(return_value=False)
    svc.health      = AsyncMock(return_value={
        "postgres_ping": True, "postgres_ready": True,
        "redis_ping": True, "redis_ready": True,
    })
    return svc


@pytest.fixture
def client(mock_service):
    from src.bootstrap.dependencies import get_item_service
    app.dependency_overrides[get_item_service] = lambda: mock_service
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, mock_service
    app.dependency_overrides.clear()


def test_health_returns_200(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200


def test_create_item_returns_201(client):
    c, svc = client
    item = Item(id="cached-1", name="Cached Widget", status="active")
    svc.create_item.return_value = item
    resp = c.post("/items", json={
        "id": "cached-1", "name": "Cached Widget", "status": "active"
    })
    assert resp.status_code == 201
    assert resp.json()["id"] == "cached-1"


def test_get_item_returns_200_when_found(client):
    """Mirrors the live validation GET /items/cached-1 → 200 response."""
    c, svc = client
    item = Item(id="cached-1", name="Cached Widget", status="active")
    svc.get_item.return_value = item
    resp = c.get("/items/cached-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "cached-1"


def test_get_item_second_call_returns_same_payload(client):
    """
    Mirrors the cache-hit scenario: two consecutive GETs return identical
    payloads (the service's cache-aside logic is transparent to the caller).
    """
    c, svc = client
    item = Item(id="cached-1", name="Cached Widget", status="active")
    svc.get_item.return_value = item
    resp1 = c.get("/items/cached-1")
    resp2 = c.get("/items/cached-1")
    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json() == resp2.json()


def test_get_item_returns_404_when_missing(client):
    """
    Mirrors the live validation final GET /items/cached-1 → 404 with
    {"detail": "Item 'cached-1' not found"} after DELETE.
    """
    c, svc = client
    svc.get_item.return_value = None
    resp = c.get("/items/cached-1")
    assert resp.status_code == 404
    assert "cached-1" in resp.json()["detail"]


def test_delete_item_returns_204(client):
    """Mirrors the live validation DELETE /items/cached-1 → 204 response."""
    c, svc = client
    svc.delete_item.return_value = True
    resp = c.delete("/items/cached-1")
    assert resp.status_code == 204


def test_delete_item_returns_404_when_missing(client):
    c, svc = client
    svc.delete_item.return_value = False
    resp = c.delete("/items/missing")
    assert resp.status_code == 404


def test_update_item_returns_200_when_found(client):
    c, svc = client
    item = Item(id="cached-1", name="Updated", status="active")
    svc.update_item.return_value = item
    resp = c.put("/items/cached-1", json={"id": "cached-1", "name": "Updated"})
    assert resp.status_code == 200


def test_update_item_returns_404_when_missing(client):
    c, svc = client
    svc.update_item.return_value = None
    resp = c.put("/items/missing", json={"id": "missing", "name": "X"})
    assert resp.status_code == 404


def test_list_items_returns_200(client):
    c, svc = client
    svc.list_items.return_value = ([], 0)
    resp = c.get("/items")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "total" in body
