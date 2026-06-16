from __future__ import annotations

import pytest
from src.domain.artifact import EmbeddingStatus, ResearchArtifact
from src.application.services.artifact_service import ArtifactService


async def test_ingest_sets_ingested_at(service, mock_repo, artifact_factory):
    artifact = artifact_factory()
    mock_repo.create.return_value = artifact
    await service.ingest(artifact)
    created = mock_repo.create.call_args[0][0]
    assert created.ingested_at is not None


async def test_ingest_sets_pending_status(service, mock_repo, artifact_factory):
    artifact = artifact_factory(embedding_status=EmbeddingStatus.READY)
    mock_repo.create.return_value = artifact
    await service.ingest(artifact)
    created = mock_repo.create.call_args[0][0]
    assert created.embedding_status == EmbeddingStatus.PENDING


async def test_get_artifact_delegates_to_repo(service, mock_repo, artifact_factory):
    artifact = artifact_factory()
    mock_repo.get.return_value = artifact
    result = await service.get_artifact("art-1")
    assert result == artifact
    mock_repo.get.assert_called_once_with("art-1")


async def test_get_artifact_returns_none_when_missing(service, mock_repo):
    mock_repo.get.return_value = None
    result = await service.get_artifact("missing")
    assert result is None


async def test_update_embedding_status_fetches_then_updates(
    service, mock_repo, artifact_factory
):
    artifact = artifact_factory()
    updated  = artifact_factory(embedding_status=EmbeddingStatus.READY)
    mock_repo.get.return_value    = artifact
    mock_repo.update.return_value = updated
    result = await service.update_embedding_status("art-1", EmbeddingStatus.READY)
    assert result.embedding_status == EmbeddingStatus.READY


async def test_update_embedding_status_returns_none_when_missing(service, mock_repo):
    mock_repo.get.return_value = None
    result = await service.update_embedding_status("missing", EmbeddingStatus.READY)
    assert result is None


async def test_search_delegates_to_repo(service, mock_repo, artifact_factory):
    artifacts = [artifact_factory()]
    mock_repo.search.return_value = artifacts
    result = await service.search("transformer")
    assert result == artifacts
    mock_repo.search.assert_called_once_with("transformer")


async def test_filter_by_tags_delegates_to_repo(service, mock_repo, artifact_factory):
    artifacts = [artifact_factory()]
    mock_repo.filter_by_tags.return_value = artifacts
    result = await service.filter_by_tags(["nlp"])
    assert result == artifacts
    mock_repo.filter_by_tags.assert_called_once_with(["nlp"])


async def test_service_no_adapter_imports():
    import ast
    import inspect
    import src.application.services.artifact_service as m
    source = inspect.getsource(m)
    assert "openframe.adapters" not in source
    tree = ast.parse(source)
    all_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            all_imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            all_imports.append(node.module)
    assert not any("motor" in i for i in all_imports), \
        "service imports motor — must be infrastructure-free"
