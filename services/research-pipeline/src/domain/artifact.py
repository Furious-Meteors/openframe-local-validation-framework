"""
ResearchArtifact domain entity.

Identical to artifacts-mongo service.
Preview of Research Vault Phase 1.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class EmbeddingStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    FAILED     = "failed"


class ArtifactEvent(str, Enum):
    INGESTED   = "artifact.ingested"
    PROCESSING = "artifact.processing"
    READY      = "artifact.ready"
    FAILED     = "artifact.failed"


class ResearchArtifact(BaseModel):
    id:               str
    title:            str
    source:           str
    tags:             list[str] = Field(default_factory=list)
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    abstract:         Optional[str] = None
    url:              Optional[str] = None
    ingested_at:      Optional[datetime] = None

    model_config = {"from_attributes": True}
