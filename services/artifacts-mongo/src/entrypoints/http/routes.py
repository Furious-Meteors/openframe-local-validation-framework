"""HTTP routes for the artifacts service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.services.artifact_service import ArtifactService
from src.bootstrap.dependencies import get_artifact_service
from src.domain.artifact import EmbeddingStatus, ResearchArtifact

router = APIRouter(prefix="/artifacts")


@router.get("", response_model=dict)
async def list_artifacts(
    limit:   int = Query(20, ge=1, le=100),
    offset:  int = Query(0, ge=0),
    tags:    str | None = Query(None, description="Comma-separated tags"),
    service: ArtifactService = Depends(get_artifact_service),
):
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        artifacts = await service.filter_by_tags(tag_list)
        return {"artifacts": artifacts, "total": len(artifacts)}
    artifacts, total = await service.list_artifacts(limit=limit, offset=offset)
    return {"artifacts": artifacts, "total": total}


@router.post("", response_model=ResearchArtifact, status_code=201)
async def ingest_artifact(
    artifact: ResearchArtifact,
    service:  ArtifactService = Depends(get_artifact_service),
):
    return await service.ingest(artifact)


# /search must be registered before /{artifact_id} to avoid path shadowing
@router.get("/search", response_model=list[ResearchArtifact])
async def search_artifacts(
    q:       str = Query(..., min_length=2),
    service: ArtifactService = Depends(get_artifact_service),
):
    """Full-text search using MongoDB regex — niche motor feature."""
    return await service.search(q)


@router.get("/{artifact_id}", response_model=ResearchArtifact)
async def get_artifact(
    artifact_id: str,
    service:     ArtifactService = Depends(get_artifact_service),
):
    artifact = await service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!r} not found")
    return artifact


@router.patch("/{artifact_id}/status", response_model=ResearchArtifact)
async def update_status(
    artifact_id: str,
    status:      EmbeddingStatus,
    service:     ArtifactService = Depends(get_artifact_service),
):
    updated = await service.update_embedding_status(artifact_id, status)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!r} not found")
    return updated


@router.delete("/{artifact_id}", status_code=204)
async def delete_artifact(
    artifact_id: str,
    service:     ArtifactService = Depends(get_artifact_service),
):
    deleted = await service.delete_artifact(artifact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!r} not found")
