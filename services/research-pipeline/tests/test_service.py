"""
Tests for ResearchPipelineService — the orchestration logic.

Proves the three-step ingest flow, the Redis-first/MongoDB-fallback
status pattern, and graceful degradation when Kafka or Redis fails.
"""
from __future__ import annotations

import pytest
from openframe.core.ports import PluginHealth, PluginStatus

from src.domain.artifact import ArtifactEvent, EmbeddingStatus, ResearchArtifact


# ── ingest() — the three-step flow ──────────────────────────────────────────

async def test_ingest_stores_in_persistence_first(
    service, mock_persistence, artifact_factory
):
    artifact = artifact_factory()
    mock_persistence.create.return_value = artifact
    await service.ingest(artifact)
    mock_persistence.create.assert_called_once()


async def test_ingest_sets_ingested_at(service, mock_persistence, artifact_factory):
    artifact = artifact_factory()
    mock_persistence.create.return_value = artifact
    await service.ingest(artifact)
    stored_arg = mock_persistence.create.call_args[0][0]
    assert stored_arg.ingested_at is not None


async def test_ingest_sets_pending_status_regardless_of_input(
    service, mock_persistence, artifact_factory
):
    artifact = artifact_factory(embedding_status=EmbeddingStatus.READY)
    mock_persistence.create.return_value = artifact
    await service.ingest(artifact)
    stored_arg = mock_persistence.create.call_args[0][0]
    assert stored_arg.embedding_status == EmbeddingStatus.PENDING


async def test_ingest_publishes_event_to_kafka(
    service, mock_persistence, mock_publisher, artifact_factory
):
    artifact = artifact_factory(id="art-99")
    mock_persistence.create.return_value = artifact
    await service.ingest(artifact)
    mock_publisher.publish.assert_called_once()
    published = mock_publisher.publish.call_args[0][0]
    assert published["event_type"] == ArtifactEvent.INGESTED
    assert published["artifact_id"] == "art-99"


async def test_ingest_caches_status_in_redis(
    service, mock_persistence, mock_cache, artifact_factory
):
    artifact = artifact_factory(id="art-1")
    mock_persistence.create.return_value = artifact
    await service.ingest(artifact)
    mock_cache.create.assert_called_once()
    cached_arg = mock_cache.create.call_args[0][0]
    assert cached_arg.id == "status:art-1"


async def test_ingest_returns_stored_artifact(
    service, mock_persistence, artifact_factory
):
    artifact = artifact_factory()
    mock_persistence.create.return_value = artifact
    result = await service.ingest(artifact)
    assert result == artifact


# ── Graceful degradation ────────────────────────────────────────────────────

async def test_ingest_succeeds_when_kafka_publish_fails(
    service, mock_persistence, mock_publisher, artifact_factory
):
    """If Kafka is down, the artifact is still stored in MongoDB."""
    artifact = artifact_factory()
    mock_persistence.create.return_value = artifact
    mock_publisher.publish.side_effect = Exception("Kafka unreachable")
    result = await service.ingest(artifact)
    assert result == artifact


async def test_ingest_succeeds_when_redis_cache_fails(
    service, mock_persistence, mock_cache, artifact_factory
):
    """If Redis is down, the artifact is still stored in MongoDB."""
    artifact = artifact_factory()
    mock_persistence.create.return_value = artifact
    mock_cache.create.side_effect = Exception("Redis unreachable")
    result = await service.ingest(artifact)
    assert result == artifact


# ── get_status() — Redis-first, MongoDB-fallback ────────────────────────────

async def test_get_status_returns_redis_when_cache_hit(
    service, mock_cache, artifact_factory
):
    cached = artifact_factory(embedding_status=EmbeddingStatus.PROCESSING)
    mock_cache.get.return_value = cached
    result = await service.get_status("art-1")
    assert result["source"] == "redis_cache"
    assert result["embedding_status"] == EmbeddingStatus.PROCESSING


async def test_get_status_falls_back_to_mongodb_on_cache_miss(
    service, mock_cache, mock_persistence, artifact_factory
):
    mock_cache.get.return_value = None
    artifact = artifact_factory(embedding_status=EmbeddingStatus.READY)
    mock_persistence.get.return_value = artifact
    result = await service.get_status("art-1")
    assert result["source"] == "mongodb"
    assert result["embedding_status"] == EmbeddingStatus.READY


async def test_get_status_falls_back_to_mongodb_when_redis_raises(
    service, mock_cache, mock_persistence, artifact_factory
):
    """If Redis itself errors (not just a miss), fall through to MongoDB."""
    mock_cache.get.side_effect = Exception("Redis connection lost")
    artifact = artifact_factory()
    mock_persistence.get.return_value = artifact
    result = await service.get_status("art-1")
    assert result["source"] == "mongodb"


async def test_get_status_returns_error_when_not_found_anywhere(
    service, mock_cache, mock_persistence
):
    mock_cache.get.return_value = None
    mock_persistence.get.return_value = None
    result = await service.get_status("missing")
    assert "error" in result


async def test_get_status_uses_correct_cache_key_format(
    service, mock_cache, artifact_factory
):
    mock_cache.get.return_value = None
    await service.get_status("art-42")
    mock_cache.get.assert_called_once_with("status:art-42")


# ── update_status() ──────────────────────────────────────────────────────────

async def test_update_status_returns_none_when_artifact_missing(
    service, mock_persistence
):
    mock_persistence.get.return_value = None
    result = await service.update_status("missing", EmbeddingStatus.READY)
    assert result is None


async def test_update_status_updates_persistence(
    service, mock_persistence, artifact_factory
):
    artifact = artifact_factory(embedding_status=EmbeddingStatus.PENDING)
    updated  = artifact_factory(embedding_status=EmbeddingStatus.READY)
    mock_persistence.get.return_value    = artifact
    mock_persistence.update.return_value = updated
    result = await service.update_status("art-1", EmbeddingStatus.READY)
    assert result.embedding_status == EmbeddingStatus.READY


async def test_update_status_invalidates_redis_cache(
    service, mock_persistence, mock_cache, artifact_factory
):
    artifact = artifact_factory()
    mock_persistence.get.return_value    = artifact
    mock_persistence.update.return_value = artifact
    await service.update_status("art-1", EmbeddingStatus.READY)
    mock_cache.delete.assert_called_once_with("status:art-1")


async def test_update_status_succeeds_when_cache_invalidation_fails(
    service, mock_persistence, mock_cache, artifact_factory
):
    """Graceful degradation — cache invalidation failure doesn't break the update."""
    artifact = artifact_factory()
    mock_persistence.get.return_value    = artifact
    mock_persistence.update.return_value = artifact
    mock_cache.delete.side_effect = Exception("Redis down")
    result = await service.update_status("art-1", EmbeddingStatus.READY)
    assert result is not None


# ── list_artifacts() and health() ───────────────────────────────────────────

async def test_list_artifacts_reads_from_persistence_only(
    service, mock_persistence, artifact_factory
):
    artifacts = [artifact_factory(id="1"), artifact_factory(id="2")]
    mock_persistence.list.return_value = (artifacts, 2)
    result_items, total = await service.list_artifacts(limit=10, offset=0)
    assert total == 2
    mock_persistence.list.assert_called_once_with(limit=10, offset=0)


async def test_health_checks_persistence_and_cache(
    service, mock_persistence, mock_cache
):
    mock_persistence.health.return_value = PluginHealth(status=PluginStatus.READY)
    mock_cache.health.return_value       = PluginHealth(status=PluginStatus.READY)
    result = await service.health()
    assert result == {"mongodb_ping": True, "redis_ping": True}


def test_service_no_adapter_imports():
    import src.application.services.pipeline_service as m, inspect
    source = inspect.getsource(m)
    assert "openframe.adapters" not in source
    assert "motor" not in source
    assert "aiokafka" not in source
