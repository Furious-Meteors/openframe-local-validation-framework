"""Artifact application service."""
from __future__ import annotations

from datetime import datetime, timezone

from openframe.core.ports import PluginStatus

from src.application.ports.artifact_repository import ArtifactRepositoryPort
from src.domain.artifact import EmbeddingStatus, ResearchArtifact


class ArtifactService:
    def __init__(self, repository: ArtifactRepositoryPort) -> None:
        self._repo = repository

    async def ingest(self, artifact: ResearchArtifact) -> ResearchArtifact:
        """
        Ingest a new research artifact.
        Sets ingested_at and initial embedding_status.
        """
        artifact = artifact.model_copy(update={
            "ingested_at":      datetime.now(timezone.utc),
            "embedding_status": EmbeddingStatus.PENDING,
        })
        return await self._repo.create(artifact)

    async def get_artifact(self, artifact_id: str) -> ResearchArtifact | None:
        return await self._repo.get(artifact_id)

    async def list_artifacts(
        self, limit: int = 20, offset: int = 0,
    ) -> tuple[list[ResearchArtifact], int]:
        return await self._repo.list(limit=limit, offset=offset)

    async def update_embedding_status(
        self,
        artifact_id: str,
        status: EmbeddingStatus,
    ) -> ResearchArtifact | None:
        artifact = await self._repo.get(artifact_id)
        if artifact is None:
            return None
        updated = artifact.model_copy(update={"embedding_status": status})
        return await self._repo.update(updated)

    async def delete_artifact(self, artifact_id: str) -> bool:
        return await self._repo.delete(artifact_id)

    async def search(self, query: str) -> list[ResearchArtifact]:
        """Full-text search — uses niche motor feature in the adapter."""
        return await self._repo.search(query)

    async def filter_by_tags(self, tags: list[str]) -> list[ResearchArtifact]:
        """Tag filter — uses MongoDB $in query in the adapter."""
        return await self._repo.filter_by_tags(tags)

    async def health(self) -> dict:
        health = await self._repo.health()
        ready = health.status == PluginStatus.READY
        return {"ping": ready, "is_ready": ready}
