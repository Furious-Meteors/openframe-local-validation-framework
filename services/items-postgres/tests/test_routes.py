"""
Tests for HTTP routes.

Uses FastAPI TestClient with mocked ItemService.
Proves correct status codes and response shapes.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from unittest.mock import patch

from src.domain.item import Item
from src.entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.get_item         = AsyncMock(return_value=None)
    svc.list_items       = AsyncMock(return_value=([], 0))
    svc.create_item      = AsyncMock()
    svc.update_item      = AsyncMock(return_value=None)
    svc.delete_item      = AsyncMock(return_value=False)
    svc.filter_by_status = AsyncMock(return_value=[])
    svc.bulk_import      = AsyncMock(return_value=0)
    svc.health           = AsyncMock(return_value={"ping": True, "is_ready": True})
    return svc


@pytest.fixture
def client(mock_service):
    from src.bootstrap.dependencies import get_item_service
    app.dependency_overrides[get_item_service] = lambda: mock_service
    with patch("src.entrypoints.http.main.get_item_service", return_value=mock_service):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_service
    app.dependency_overrides.clear()


# ── GET /health ────────────────────────────────────────────────────────────

def test_health_returns_200(client):
    c, svc = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_health_degraded_when_ping_false(client):
    c, svc = client
    svc.health.return_value = {"ping": False, "is_ready": True}
    resp = c.get("/health")
    assert resp.json()["status"] == "degraded"


# ── GET /items ─────────────────────────────────────────────────────────────

def test_list_items_returns_200(client):
    c, svc = client
    svc.list_items.return_value = ([], 0)
    resp = c.get("/items")
    assert resp.status_code == 200


def test_list_items_returns_items_and_total(client):
    c, svc = client
    item = Item(id="1", name="Widget", status="active")
    svc.list_items.return_value = ([item], 1)
    resp = c.get("/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_list_items_with_status_filter_calls_filter_by_status(client):
    c, svc = client
    item = Item(id="1", name="Widget", status="inactive")
    svc.filter_by_status.return_value = [item]
    resp = c.get("/items?status=inactive")
    assert resp.status_code == 200
    svc.filter_by_status.assert_called_once_with("inactive")


def test_list_items_pagination_params(client):
    c, svc = client
    svc.list_items.return_value = ([], 0)
    c.get("/items?limit=10&offset=5")
    svc.list_items.assert_called_once_with(limit=10, offset=5)


# ── POST /items ────────────────────────────────────────────────────────────

def test_create_item_returns_201(client):
    c, svc = client
    item = Item(id="abc", name="Widget")
    svc.create_item.return_value = item
    resp = c.post("/items", json={"id": "abc", "name": "Widget"})
    assert resp.status_code == 201
    assert resp.json()["id"] == "abc"


def test_create_item_missing_name_returns_422(client):
    c, _ = client
    resp = c.post("/items", json={"id": "abc"})
    assert resp.status_code == 422


# ── GET /items/{id} ────────────────────────────────────────────────────────

def test_get_item_returns_200_when_found(client):
    c, svc = client
    item = Item(id="abc", name="Widget")
    svc.get_item.return_value = item
    resp = c.get("/items/abc")
    assert resp.status_code == 200
    assert resp.json()["id"] == "abc"


def test_get_item_returns_404_when_missing(client):
    c, svc = client
    svc.get_item.return_value = None
    resp = c.get("/items/missing")
    assert resp.status_code == 404


# ── PUT /items/{id} ────────────────────────────────────────────────────────

def test_update_item_returns_200_when_found(client):
    c, svc = client
    item = Item(id="abc", name="Widget")
    svc.update_item.return_value = item
    resp = c.put("/items/abc", json={"id": "abc", "name": "Widget"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "abc"


def test_update_item_returns_404_when_missing(client):
    c, svc = client
    svc.update_item.return_value = None
    resp = c.put("/items/missing", json={"id": "missing", "name": "X"})
    assert resp.status_code == 404


# ── DELETE /items/{id} ─────────────────────────────────────────────────────

def test_delete_item_returns_204_when_deleted(client):
    c, svc = client
    svc.delete_item.return_value = True
    resp = c.delete("/items/abc")
    assert resp.status_code == 204


def test_delete_item_returns_404_when_missing(client):
    c, svc = client
    svc.delete_item.return_value = False
    resp = c.delete("/items/missing")
    assert resp.status_code == 404


# ── POST /items/bulk ───────────────────────────────────────────────────────

def test_bulk_import_returns_201(client):
    c, svc = client
    svc.bulk_import.return_value = 3
    resp = c.post("/items/bulk", json=[
        {"id": "1", "name": "A"},
        {"id": "2", "name": "B"},
        {"id": "3", "name": "C"},
    ])
    assert resp.status_code == 201
    assert resp.json()["imported"] == 3
