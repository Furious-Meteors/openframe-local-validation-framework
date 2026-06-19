"""
Tests for the three outbound adapters.

ArtifactMongoRepository, ArtifactRedisCache, ArtifactEventProducer.
"""
from __future__ import annotations

import json
import pytest

from openframe.core.health import HealthCheck
from openframe.core.ports import BaseProducer, BaseRepository

from src.domain.artifact import EmbeddingStatus, ResearchArtifact


# ── ArtifactMongoRepository ──────────────────────────────────────────────────

def test_mongo_adapter_satisfies_base_repository(mongo_adapter):
    repo, _, _ = mongo_adapter
    assert isinstance(repo, BaseRepository)


def test_mongo_adapter_satisfies_health_check(mongo_adapter):
    repo, _, _ = mongo_adapter
    assert isinstance(repo, HealthCheck)


def test_mongo_collection_name(mongo_adapter):
    repo, _, _ = mongo_adapter
    assert repo._collection == "artifacts"


def test_mongo_doc_to_entity(mongo_adapter):
    repo, _, _ = mongo_adapter
    doc = {
        "id": "art-1", "_id": "art-1", "title": "Paper", "source": "arxiv",
        "tags": ["nlp"], "embedding_status": "ready",
        "abstract": None, "url": None, "ingested_at": None,
    }
    artifact = repo._doc_to_entity(doc)
    assert isinstance(artifact, ResearchArtifact)
    assert artifact.embedding_status == EmbeddingStatus.READY


def test_mongo_entity_to_doc(mongo_adapter, artifact_factory):
    repo, _, _ = mongo_adapter
    artifact = artifact_factory()
    doc = repo._entity_to_doc(artifact)
    assert doc["_id"] == artifact.id
    assert doc["embedding_status"] == "pending"


# ── ArtifactRedisCache ───────────────────────────────────────────────────────

def test_redis_adapter_satisfies_base_repository(redis_adapter):
    repo, _ = redis_adapter
    assert isinstance(repo, BaseRepository)


def test_redis_adapter_satisfies_health_check(redis_adapter):
    repo, _ = redis_adapter
    assert isinstance(repo, HealthCheck)


def test_redis_dict_to_entity_minimal_fields(redis_adapter):
    """ArtifactRedisCache stores only id/title/source/embedding_status — lightweight."""
    repo, _ = redis_adapter
    data = {"id": "status:art-1", "title": "Paper", "source": "arxiv",
            "embedding_status": "processing"}
    artifact = repo._dict_to_entity(data)
    assert artifact.id == "status:art-1"
    assert artifact.embedding_status == EmbeddingStatus.PROCESSING


def test_redis_entity_to_dict_excludes_tags_and_abstract(redis_adapter, artifact_factory):
    """The status cache is intentionally lightweight — no tags/abstract/url."""
    repo, _ = redis_adapter
    artifact = artifact_factory()
    data = repo._entity_to_dict(artifact)
    assert "tags" not in data
    assert "abstract" not in data
    assert set(data.keys()) == {"id", "title", "source", "embedding_status"}


async def test_redis_get_returns_none_on_miss(redis_adapter):
    repo, client = redis_adapter
    client.get.return_value = None
    result = await repo.get("status:missing")
    assert result is None


# ── ArtifactEventProducer ────────────────────────────────────────────────────

def test_kafka_producer_satisfies_base_producer(kafka_adapter):
    producer, _ = kafka_adapter
    assert isinstance(producer, BaseProducer)


def test_kafka_serialise_produces_json_bytes_with_default_str(kafka_adapter):
    """
    _serialise uses json.dumps(..., default=str) — handles ArtifactEvent enum
    and datetime objects that plain json.dumps would reject.
    """
    producer, _ = kafka_adapter
    message = {
        "event_type":  "artifact.ingested",
        "artifact_id": "art-1",
        "occurred_at": "2026-01-01T00:00:00+00:00",
    }
    raw = producer._serialise(message)
    assert isinstance(raw, bytes)
    decoded = json.loads(raw.decode("utf-8"))
    assert decoded["artifact_id"] == "art-1"


async def test_kafka_publish_calls_send_and_wait(kafka_adapter):
    producer, mock_client = kafka_adapter
    await producer.publish({"event_type": "artifact.ingested", "artifact_id": "x"})
    mock_client.send_and_wait.assert_called_once()
    call_args = mock_client.send_and_wait.call_args
    assert call_args[0][0] == "artifact-events"
