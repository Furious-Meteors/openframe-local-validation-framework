"""HTTP routes for the research pipeline."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.services.pipeline_service import ResearchPipelineService
from src.bootstrap.dependencies import get_pipeline_service
from src.domain.artifact import EmbeddingStatus, ResearchArtifact

router = APIRouter(prefix="/artifacts")


@router.post("", response_model=ResearchArtifact, status_code=201)
async def ingest_artifact(
    artifact: ResearchArtifact,
    service:  ResearchPipelineService = Depends(get_pipeline_service),
):
    """
    Ingest a research artifact.

    Flow: MongoDB store → Kafka publish → Redis cache
    All three adapters work in one request.
    """
    return await service.ingest(artifact)


@router.get("", response_model=dict)
async def list_artifacts(
    limit:   int = Query(20, ge=1, le=100),
    offset:  int = Query(0, ge=0),
    service: ResearchPipelineService = Depends(get_pipeline_service),
):
    artifacts, total = await service.list_artifacts(limit=limit, offset=offset)
    return {"artifacts": artifacts, "total": total}


@router.get("/{artifact_id}", response_model=ResearchArtifact)
async def get_artifact(
    artifact_id: str,
    service:     ResearchPipelineService = Depends(get_pipeline_service),
):
    artifact = await service.get_artifact(artifact_id)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!r} not found")
    return artifact


@router.get("/{artifact_id}/status")
async def status(
    artifact_id: str,
    service:     ResearchPipelineService = Depends(get_pipeline_service),
):
    """
    Get embedding status — Redis first, MongoDB fallback.

    The 'source' field in the response shows which backend served it:
        "redis_cache" — fast path, status was cached
        "mongodb"     — slow path, cache miss or Redis unavailable
    """
    return await service.get_status(artifact_id)


@router.patch("/{artifact_id}/status", response_model=ResearchArtifact)
async def update_status(
    artifact_id: str,
    status:      EmbeddingStatus,
    service:     ResearchPipelineService = Depends(get_pipeline_service),
):
    """Update embedding status. Invalidates Redis cache."""
    result = await service.update_status(artifact_id, status)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Artifact {artifact_id!r} not found")
    return result
