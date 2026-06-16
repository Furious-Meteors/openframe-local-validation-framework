from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.artifact import EmbeddingStatus, ResearchArtifact
from src.entrypoints.http.main import app


@pytest.fixture
def mock_service():
    svc = MagicMock()
    svc.ingest                  = AsyncMock()
    svc.get_artifact            = AsyncMock(return_value=None)
    svc.list_artifacts          = AsyncMock(return_value=([], 0))
    svc.update_embedding_status = AsyncMock(return_value=None)
    svc.delete_artifact         = AsyncMock(return_value=False)
    svc.search                  = AsyncMock(return_value=[])
    svc.filter_by_tags          = AsyncMock(return_value=[])
    svc.health                  = AsyncMock(return_value={"ping": True, "is_ready": True})
    return svc


@pytest.fixture
def client(mock_service, monkeypatch):
    monkeypatch.setenv("MONGO_URL", "mongodb://test:test@localhost:27017")
    monkeypatch.setenv("MONGO_DATABASE", "test_db")
    from src.bootstrap.dependencies import _get_settings, _get_repository, get_artifact_service
    _get_settings.cache_clear()
    _get_repository.cache_clear()
    app.dependency_overrides[get_artifact_service] = lambda: mock_service
    with patch("src.entrypoints.http.main.get_artifact_service", return_value=mock_service):
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c, mock_service
    app.dependency_overrides.clear()
    _get_settings.cache_clear()
    _get_repository.cache_clear()


def test_health_returns_200(client):
    c, _ = client
    resp = c.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ingest_artifact_returns_201(client):
    c, svc = client
    artifact = ResearchArtifact(id="art-1", title="Paper", source="arxiv")
    svc.ingest.return_value = artifact
    resp = c.post("/artifacts", json={"id": "art-1", "title": "Paper", "source": "arxiv"})
    assert resp.status_code == 201


def test_get_artifact_returns_200(client):
    c, svc = client
    artifact = ResearchArtifact(id="art-1", title="Paper", source="arxiv")
    svc.get_artifact.return_value = artifact
    resp = c.get("/artifacts/art-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "art-1"


def test_get_artifact_returns_404(client):
    c, svc = client
    svc.get_artifact.return_value = None
    resp = c.get("/artifacts/missing")
    assert resp.status_code == 404


def test_search_returns_200(client):
    c, svc = client
    svc.search.return_value = []
    resp = c.get("/artifacts/search?q=transformer")
    assert resp.status_code == 200


def test_search_requires_min_length(client):
    c, _ = client
    resp = c.get("/artifacts/search?q=a")
    assert resp.status_code == 422


def test_list_with_tags_calls_filter(client):
    c, svc = client
    svc.filter_by_tags.return_value = []
    resp = c.get("/artifacts?tags=nlp,ml")
    assert resp.status_code == 200
    svc.filter_by_tags.assert_called_once_with(["nlp", "ml"])


def test_delete_artifact_returns_204(client):
    c, svc = client
    svc.delete_artifact.return_value = True
    resp = c.delete("/artifacts/art-1")
    assert resp.status_code == 204


def test_delete_artifact_returns_404(client):
    c, svc = client
    svc.delete_artifact.return_value = False
    resp = c.delete("/artifacts/missing")
    assert resp.status_code == 404
