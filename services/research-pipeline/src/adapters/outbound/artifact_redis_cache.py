"""Redis adapter for artifact status caching."""
from __future__ import annotations

from typing import Any

from openframe.adapters.db.redis import RedisRepository
from src.domain.artifact import EmbeddingStatus, ResearchArtifact


class ArtifactRedisCache(RedisRepository[ResearchArtifact]):
    """
    Artifact status cache backed by Redis.

    Stores lightweight status-only documents under keys:
        artifact-status:status:{artifact_id}

    Full artifact documents live in MongoDB only.
    Redis stores just enough for fast status lookups.
    """

    def _dict_to_entity(self, data: dict[str, Any]) -> ResearchArtifact:
        return ResearchArtifact(
            id=data["id"],
            title=data.get("title", ""),
            source=data.get("source", ""),
            embedding_status=EmbeddingStatus(data.get("embedding_status", "pending")),
        )

    def _entity_to_dict(self, entity: ResearchArtifact) -> dict[str, Any]:
        return {
            "id":               entity.id,
            "title":            entity.title,
            "source":           entity.source,
            "embedding_status": entity.embedding_status.value,
        }
