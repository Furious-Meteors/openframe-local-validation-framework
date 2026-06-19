"""
Tests for HTTP routes.

Uses FastAPI TestClient with mocked ResearchPipelineService.
TestClient(app) triggers the real lifespan — the autouse _test_env
fixture in conftest.py plus the ValidationError/AdapterConnectionError
handling in main.py's lifespan ensure this never attempts a real
network connection during tests.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from src.domain.artifact import EmbeddingStatus, ResearchArtifact
from src.entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.ingest          = AsyncMock()
    svc.get_artifact    = AsyncMock(return_value=None)
    svc.list_artifacts  = AsyncMock(return_value=([], 0))
    svc.get_status      = AsyncMock(return_value={})
    svc.update_status   = AsyncMock(return_value=None)
    svc.health          = AsyncMock(return_value={"mongodb_ping": True, "redis_ping": True})
    return svc


@pytest.fixture
def client(mock_service):
    from src.bootstrap.dependencies import get_pipeline_service
    app.dependency_overrides[get_pipeline_service] = lambda: mock_service
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c, mock_service
    app.dependency_overrides.clear()


def test_health_returns_200(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200


def test_pipeline_info_returns_200(client):
    c, _ = client
    resp = c.get("/pipeline-info")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["adapters"]) == 3
    assert body["adapters"][0]["capability"] == "persistence"
    assert body["adapters"][1]["capability"] == "cache"
    assert body["adapters"][2]["capability"] == "queue"


def test_ingest_artifact_returns_201(client):
    c, svc = client
    artifact = ResearchArtifact(id="art-1", title="Paper", source="arxiv")
    svc.ingest.return_value = artifact
    resp = c.post("/artifacts", json={
        "id": "art-1", "title": "Paper", "source": "arxiv"
    })
    assert resp.status_code == 201


def test_list_artifacts_returns_200(client):
    c, svc = client
    svc.list_artifacts.return_value = ([], 0)
    resp = c.get("/artifacts")
    assert resp.status_code == 200


def test_get_artifact_returns_200_when_found(client):
    c, svc = client
    artifact = ResearchArtifact(id="art-1", title="Paper", source="arxiv")
    svc.get_artifact.return_value = artifact
    resp = c.get("/artifacts/art-1")
    assert resp.status_code == 200


def test_get_artifact_returns_404_when_missing(client):
    c, svc = client
    svc.get_artifact.return_value = None
    resp = c.get("/artifacts/missing")
    assert resp.status_code == 404


def test_get_status_returns_200(client):
    c, svc = client
    svc.get_status.return_value = {
        "artifact_id":      "art-1",
        "embedding_status": "pending",
        "source":           "redis_cache",
    }
    resp = c.get("/artifacts/art-1/status")
    assert resp.status_code == 200
    assert resp.json()["source"] == "redis_cache"


def test_update_status_returns_200_when_found(client):
    c, svc = client
    artifact = ResearchArtifact(id="art-1", title="Paper", source="arxiv",
                                embedding_status=EmbeddingStatus.READY)
    svc.update_status.return_value = artifact
    resp = c.patch("/artifacts/art-1/status?status=ready")
    assert resp.status_code == 200


def test_update_status_returns_404_when_missing(client):
    c, svc = client
    svc.update_status.return_value = None
    resp = c.patch("/artifacts/missing/status?status=ready")
    assert resp.status_code == 404
