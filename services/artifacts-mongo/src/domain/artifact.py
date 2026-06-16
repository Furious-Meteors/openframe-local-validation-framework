"""
ResearchArtifact domain entity.

Represents a research artifact from sources like arXiv, Hugging Face,
or GitHub. This is a preview of Research Vault Phase 1.

Pure Python — no database, no framework imports.
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


class ResearchArtifact(BaseModel):
    """
    A research artifact from an external source.

    id:               Caller-supplied identifier (slug or UUID).
    title:            Full title of the artifact.
    source:           Origin — "arxiv", "huggingface", "github".
    tags:             Topic tags for categorisation and filtering.
    embedding_status: Processing lifecycle for the embedding pipeline.
    abstract:         Optional abstract or description.
    url:              Optional link to the original artifact.
    ingested_at:      Set on ingestion.
    """

    id:               str
    title:            str
    source:           str
    tags:             list[str] = Field(default_factory=list)
    embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING
    abstract:         Optional[str] = None
    url:              Optional[str] = None
    ingested_at:      Optional[datetime] = None

    model_config = {"from_attributes": True}
