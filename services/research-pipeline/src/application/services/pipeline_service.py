"""
Research pipeline service.

Orchestrates a three-adapter flow:
    1. MongoDB  — store artifact (persistence)
    2. Kafka    — publish ingestion event (queue)
    3. Redis    — cache artifact status (cache)

Status lookup uses Redis-first pattern:
    1. Check Redis cache (fast — sub-millisecond)
    2. On miss → read from MongoDB (accurate — source of truth)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from openframe.core.ports import PluginStatus

from src.application.ports.artifact_repository import ArtifactRepositoryPort
from src.application.ports.event_publisher     import EventPublisherPort
from src.domain.artifact import ArtifactEvent, EmbeddingStatus, ResearchArtifact

_logger = logging.getLogger(__name__)

# Redis status cache key prefix
_STATUS_KEY = "status"


class ResearchPipelineService:
    """
    Orchestrates artifact ingestion across three adapters.

    Dependencies injected via constructor — never imports adapters directly.
    """

    def __init__(
        self,
        persistence: ArtifactRepositoryPort,  # MongoDB
        cache:       ArtifactRepositoryPort,  # Redis (status cache)
        publisher:   EventPublisherPort,       # Kafka
    ) -> None:
        self._persistence = persistence
        self._cache       = cache
        self._publisher   = publisher

    async def ingest(self, artifact: ResearchArtifact) -> ResearchArtifact:
        """
        Ingest a research artifact through the full pipeline.

        Step 1: Store in MongoDB (source of truth)
        Step 2: Publish artifact.ingested event to Kafka
        Step 3: Cache initial status in Redis

        If Kafka or Redis fails, the artifact is still stored in MongoDB.
        The pipeline degrades gracefully.
        """
        # Step 1: Persist in MongoDB
        artifact = artifact.model_copy(update={
            "ingested_at":      datetime.now(timezone.utc),
            "embedding_status": EmbeddingStatus.PENDING,
        })
        stored = await self._persistence.create(artifact)
        _logger.info("Artifact stored: %s", stored.id)

        # Step 2: Publish event to Kafka
        try:
            await self._publisher.publish({
                "event_type":  ArtifactEvent.INGESTED,
                "artifact_id": stored.id,
                "source":      stored.source,
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            })
            _logger.info("Event published: artifact.ingested for %s", stored.id)
        except Exception as exc:
            _logger.warning("Kafka publish failed (degraded): %s", exc)

        # Step 3: Cache status in Redis
        try:
            status_doc = ResearchArtifact(
                id=f"{_STATUS_KEY}:{stored.id}",
                title=stored.title,
                source=stored.source,
                embedding_status=EmbeddingStatus.PENDING,
            )
            await self._cache.create(status_doc)
            _logger.info("Status cached in Redis for %s", stored.id)
        except Exception as exc:
            _logger.warning("Redis cache failed (degraded): %s", exc)

        return stored

    async def get_artifact(self, artifact_id: str) -> ResearchArtifact | None:
        """Read from MongoDB."""
        return await self._persistence.get(artifact_id)

    async def get_status(self, artifact_id: str) -> dict[str, Any]:
        """
        Get embedding status — Redis first, MongoDB fallback.

        Redis is the fast path (sub-millisecond).
        MongoDB is the accurate fallback when Redis misses or is unavailable.
        """
        # Fast path — Redis cache
        try:
            cache_key = f"{_STATUS_KEY}:{artifact_id}"
            cached = await self._cache.get(cache_key)
            if cached is not None:
                return {
                    "artifact_id":      artifact_id,
                    "embedding_status": cached.embedding_status,
                    "source":           "redis_cache",
                }
        except Exception as exc:
            _logger.warning("Redis status lookup failed: %s", exc)

        # Slow path — MongoDB
        artifact = await self._persistence.get(artifact_id)
        if artifact is None:
            return {"artifact_id": artifact_id, "error": "not found"}
        return {
            "artifact_id":      artifact_id,
            "embedding_status": artifact.embedding_status,
            "source":           "mongodb",
        }

    async def update_status(
        self,
        artifact_id: str,
        status: EmbeddingStatus,
    ) -> ResearchArtifact | None:
        """
        Update embedding status in MongoDB and invalidate Redis cache.

        Called by the background Kafka consumer when processing completes.
        """
        artifact = await self._persistence.get(artifact_id)
        if artifact is None:
            return None

        updated = artifact.model_copy(update={"embedding_status": status})
        result = await self._persistence.update(updated)

        # Invalidate Redis cache — next status check reads from MongoDB
        try:
            await self._cache.delete(f"{_STATUS_KEY}:{artifact_id}")
        except Exception as exc:
            _logger.warning("Redis invalidation failed (degraded): %s", exc)

        return result

    async def delete_artifact(self, artifact_id: str) -> bool:
        """
        Delete artifact from MongoDB and evict its Redis cache entry.
        Returns True if deleted, False if not found.
        """
        deleted = await self._persistence.delete(artifact_id)
        if deleted:
            try:
                await self._cache.delete(f"{_STATUS_KEY}:{artifact_id}")
            except Exception as exc:
                _logger.warning("Redis eviction failed (degraded): %s", exc)
        return deleted

    async def list_artifacts(
        self, limit: int = 20, offset: int = 0,
    ) -> tuple[list[ResearchArtifact], int]:
        return await self._persistence.list(limit=limit, offset=offset)

    async def health(self) -> dict:
        mongodb_health = await self._persistence.health()
        redis_health = await self._cache.health()
        return {
            "mongodb_ping": mongodb_health.status == PluginStatus.READY,
            "redis_ping":   redis_health.status == PluginStatus.READY,
        }
