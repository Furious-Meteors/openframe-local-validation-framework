from __future__ import annotations

import pytest
from openframe.core.ports import BaseRepository, Lifecycle

from src.adapters.outbound.artifact_repository import ArtifactMongoRepository
from src.domain.artifact import EmbeddingStatus, ResearchArtifact


def test_adapter_satisfies_base_repository(adapter):
    repo, _, _ = adapter
    assert isinstance(repo, BaseRepository)


def test_adapter_satisfies_health_check(adapter):
    repo, _, _ = adapter
    assert isinstance(repo, Lifecycle)


def test_collection_name_is_artifacts(adapter):
    repo, _, _ = adapter
    assert repo._collection == "artifacts"


def test_doc_to_entity_maps_all_fields(adapter):
    repo, _, _ = adapter
    doc = {
        "id": "art-1", "_id": "art-1",
        "title": "Paper", "source": "arxiv",
        "tags": ["nlp"], "embedding_status": "pending",
        "abstract": None, "url": None, "ingested_at": None,
    }
    artifact = repo._doc_to_entity(doc)
    assert isinstance(artifact, ResearchArtifact)
    assert artifact.id == "art-1"
    assert artifact.title == "Paper"
    assert artifact.embedding_status == EmbeddingStatus.PENDING


def test_entity_to_doc_maps_all_fields(adapter, artifact_factory):
    repo, _, _ = adapter
    artifact = artifact_factory()
    doc = repo._entity_to_doc(artifact)
    assert doc["_id"] == artifact.id
    assert doc["title"] == artifact.title
    assert doc["embedding_status"] == "pending"


# ── Niche feature: filter_by_tags ($in query) ─────────────────────────────

async def test_filter_by_tags_uses_in_query(adapter, artifact_factory):
    repo, col, cursor = adapter
    serialised = {
        "id": "art-1", "_id": "art-1", "title": "Paper",
        "source": "arxiv", "tags": ["nlp"], "embedding_status": "pending",
        "abstract": None, "url": None, "ingested_at": None,
    }
    cursor.to_list.return_value = [serialised]
    results = await repo.filter_by_tags(["nlp"])
    col.find.assert_called_once()
    call_filter = col.find.call_args[0][0]
    assert "$in" in str(call_filter)
    assert len(results) == 1


async def test_filter_by_tags_empty_result(adapter):
    repo, col, cursor = adapter
    cursor.to_list.return_value = []
    results = await repo.filter_by_tags(["unknown"])
    assert results == []


# ── Niche feature: search (regex) ─────────────────────────────────────────

async def test_search_uses_regex_or_query(adapter):
    repo, col, cursor = adapter
    cursor.to_list.return_value = []
    await repo.search("transformer")
    col.find.assert_called_once()
    call_filter = col.find.call_args[0][0]
    assert "$or" in call_filter


async def test_search_returns_artifacts(adapter):
    repo, col, cursor = adapter
    serialised = {
        "id": "art-1", "_id": "art-1", "title": "Attention Is All You Need",
        "source": "arxiv", "tags": ["transformer"], "embedding_status": "pending",
        "abstract": None, "url": None, "ingested_at": None,
    }
    cursor.to_list.return_value = [serialised]
    results = await repo.search("attention")
    assert len(results) == 1
    assert results[0].title == "Attention Is All You Need"
