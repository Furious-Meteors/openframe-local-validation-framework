"""MongoDB adapter for artifact persistence."""
from __future__ import annotations

from typing import Any

from openframe.adapters.db.mongo import MongoRepository
from src.domain.artifact import EmbeddingStatus, ResearchArtifact


class ArtifactMongoRepository(MongoRepository[ResearchArtifact]):
    _collection = "artifacts"

    def _doc_to_entity(self, doc: dict[str, Any]) -> ResearchArtifact:
        return ResearchArtifact(
            id=doc.get("id") or str(doc.get("_id", "")),
            title=doc["title"],
            source=doc["source"],
            tags=doc.get("tags", []),
            embedding_status=EmbeddingStatus(doc.get("embedding_status", "pending")),
            abstract=doc.get("abstract"),
            url=doc.get("url"),
            ingested_at=doc.get("ingested_at"),
        )

    def _entity_to_doc(self, entity: ResearchArtifact) -> dict[str, Any]:
        return {
            "_id":              entity.id,
            "title":            entity.title,
            "source":           entity.source,
            "tags":             entity.tags,
            "embedding_status": entity.embedding_status.value,
            "abstract":         entity.abstract,
            "url":              entity.url,
            "ingested_at":      entity.ingested_at,
        }
