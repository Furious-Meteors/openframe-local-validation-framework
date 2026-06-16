from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.publish_event      = AsyncMock()
    svc.publish_batch      = AsyncMock()
    svc.publish_keyed      = AsyncMock()
    svc.get_topic_metadata = AsyncMock(return_value={
        "topic": "test", "partition_count": 1,
        "partition_ids": [0], "bootstrap_servers": "localhost:9092",
    })
    svc.get_received = MagicMock(return_value=[])
    return svc


@pytest.fixture
def client(mock_service):
    from src.bootstrap.dependencies import get_event_service
    app.dependency_overrides[get_event_service] = lambda: mock_service
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c, mock_service
    app.dependency_overrides.clear()


def test_publish_event_returns_201(client):
    c, _ = client
    resp = c.post("/events", json={
        "order_id": "ord-1", "event_type": "created",
        "payload": {"amount": 99.99},
    })
    assert resp.status_code == 201


def test_publish_batch_returns_201(client):
    c, _ = client
    resp = c.post("/events/batch", json=[
        {"order_id": "ord-1", "event_type": "created"},
        {"order_id": "ord-2", "event_type": "updated"},
    ])
    assert resp.status_code == 201
    assert resp.json()["published"] == 2


def test_publish_keyed_returns_201(client):
    c, _ = client
    resp = c.post("/events/keyed", json={
        "order_id": "ord-1", "event_type": "created",
    })
    assert resp.status_code == 201
    assert resp.json()["key"] == "ord-1"


def test_topic_metadata_returns_200(client):
    c, _ = client
    resp = c.get("/events/metadata")
    assert resp.status_code == 200
    assert "topic" in resp.json()


def test_get_received_returns_200(client):
    c, svc = client
    svc.get_received.return_value = [
        {"order_id": "ord-1", "event_type": "created"}
    ]
    resp = c.get("/events/received")
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
