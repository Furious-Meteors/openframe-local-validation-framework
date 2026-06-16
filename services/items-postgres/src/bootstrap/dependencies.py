"""
Composition root — Stage 1 wiring.

One adapter → lru_cache direct. No PluginRegistry needed.

This is the ONLY file that imports from openframe.adapters.
Routes and services never see PostgresRepository.
"""
from __future__ import annotations

from functools import lru_cache

from openframe.adapters.db.postgres import PostgresSettings
from openframe.core.tracing import TracingProxy

from src.adapters.outbound.item_repository import ItemPostgresRepository
from src.application.services.item_service import ItemService


@lru_cache(maxsize=1)
def _get_settings() -> PostgresSettings:
    """
    Read and validate settings from env vars once per process.
    Raises pydantic_core.ValidationError at startup if DATABASE_URL is missing.
    """
    return PostgresSettings()


@lru_cache(maxsize=1)
def _get_repository() -> ItemPostgresRepository:
    """
    Construct the repository once per process.
    Pool is created lazily on first DB call via get_postgres_pool().
    """
    return ItemPostgresRepository(_get_settings())


def get_item_service() -> ItemService:
    """
    FastAPI dependency — call via Depends(get_item_service).

    TracingProxy wraps the repository so every repo method gets a child
    OTel span automatically: repository.item.get, repository.item.create, etc.
    """
    traced = TracingProxy(_get_repository(), prefix="repository.item")
    return ItemService(traced)
