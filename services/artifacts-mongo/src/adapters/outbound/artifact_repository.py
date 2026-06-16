"""
MongoDB adapter for artifact persistence.

Subclasses MongoRepository[ResearchArtifact] from openframe-adapters.
Provides domain mapping. Adds domain-specific queries using raw motor.

This is the ONLY file in the service that imports from openframe.adapters.
"""
from __future__ import annotations

import re
from typing import Any

from openframe.adapters.db.mongo import MongoRepository

from src.domain.artifact import EmbeddingStatus, ResearchArtifact


class ArtifactMongoRepository(MongoRepository[ResearchArtifact]):
    """
    ResearchArtifact repository backed by MongoDB.

    Inherits full CRUD from MongoRepository[ResearchArtifact]:
        get(), list(), create(), update(), delete(),
        ping(), is_ready(), close()

    Adds domain-specific operations:
        filter_by_tags() — MongoDB $in query via raw motor
        search()         — regex full-text search via raw motor
    """

    _collection = "artifacts"

    def _doc_to_entity(self, doc: dict[str, Any]) -> ResearchArtifact:
        """Convert MongoDB document to ResearchArtifact domain object."""
        return ResearchArtifact(
            id=doc.get("id") or str(doc.get("_id", "")),
            title=doc["title"],
            source=doc["source"],
            tags=doc.get("tags", []),
            embedding_status=EmbeddingStatus(
                doc.get("embedding_status", "pending")
            ),
            abstract=doc.get("abstract"),
            url=doc.get("url"),
            ingested_at=doc.get("ingested_at"),
        )

    def _entity_to_doc(self, entity: ResearchArtifact) -> dict[str, Any]:
        """Convert ResearchArtifact to MongoDB document."""
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

    # ── Niche feature 1: MongoDB $in query ───────────────────────────────
    # Not in BaseRepository. Uses _get_collection() for raw queries inside the adapter.

    async def filter_by_tags(self, tags: list[str]) -> list[ResearchArtifact]:
        """
        Find artifacts that have ANY of the given tags.

        MongoDB $in operator — not in BaseRepository.
        Accessed via _get_collection() — full motor query capability.
        """
        col = self._get_collection()
        docs = await col.find(
            {"tags": {"$in": tags}},
            sort=[("title", 1)],
        ).to_list(length=100)
        return [
            self._doc_to_entity(self._serialise_doc(d))
            for d in docs
        ]

    # ── Niche feature 2: Regex full-text search ───────────────────────────
    # Not in BaseRepository. Raw motor, case-insensitive regex.

    async def search(self, query: str) -> list[ResearchArtifact]:
        """
        Full-text search across title, abstract, and source.

        Uses MongoDB regex — not in BaseRepository.
        Accessed via _get_collection(). Could swap for MongoDB Atlas Search
        ($search) in production without changing the service layer.
        """
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        col = self._get_collection()
        docs = await col.find(
            {"$or": [
                {"title":    pattern},
                {"abstract": pattern},
                {"source":   pattern},
            ]}
        ).limit(20).to_list(length=20)
        return [
            self._doc_to_entity(self._serialise_doc(d))
            for d in docs
        ]
