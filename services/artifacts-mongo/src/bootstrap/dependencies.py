"""
Composition root — Stage 1 wiring.

One adapter → lru_cache direct.
"""
from __future__ import annotations

from functools import lru_cache

from openframe.adapters.db.mongo import MongoSettings
from openframe.core.tracing import TracingProxy

from src.adapters.outbound.artifact_repository import ArtifactMongoRepository
from src.application.services.artifact_service import ArtifactService


@lru_cache(maxsize=1)
def _get_settings() -> MongoSettings:
    return MongoSettings()


@lru_cache(maxsize=1)
def _get_repository() -> ArtifactMongoRepository:
    return ArtifactMongoRepository(_get_settings())


def get_artifact_service() -> ArtifactService:
    traced = TracingProxy(_get_repository(), prefix="repository.artifact")
    return ArtifactService(traced)
