"""
Composition root — Stage 1 wiring with adapter swap.

One plugin is registered at startup — chosen by PERSISTENCE_BACKEND:
    postgres (default) → PostgresPlugin  → PostgresSwapRepository
    mongo              → MongoPlugin     → MongoSwapRepository

The service (SwapItemService) and all routes are identical for both backends.
Only this file and the two adapter files know which backend is active.

This is the canonical proof that the hexagonal contract holds:
the same SwapItemRepository port, satisfied by two different adapter
implementations, selected entirely at startup without touching any
service or route code.
"""
from __future__ import annotations

import os

from openframe.adapters.db.mongo    import MongoPlugin, MongoSettings
from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
from openframe.core.plugins         import PluginRegistry
from openframe.core.tracing         import TracingProxy

from adapters.outbound.mongo_swap_repository    import MongoSwapRepository
from adapters.outbound.postgres_swap_repository import PostgresSwapRepository
from application.services.swap_item_service     import SwapItemService

_BACKEND  = os.getenv("PERSISTENCE_BACKEND", "postgres")
_registry: PluginRegistry | None = None


async def init_backends() -> None:
    """
    Register and initialise the active backend plugin.

    Called once in FastAPI lifespan on startup.
    Only one plugin is registered — the one selected by PERSISTENCE_BACKEND.
    """
    global _registry
    _registry = PluginRegistry()

    if _BACKEND == "mongo":
        _registry.register(MongoPlugin(
            MongoSettings(),
            collection="swap_items",
            repository_class=MongoSwapRepository,
        ))
    else:
        _registry.register(PostgresPlugin(
            PostgresSettings(),
            table="swap_items",
            id_column="id",
            repository_class=PostgresSwapRepository,
        ))

    await _registry.initialize_all()


async def close_backends() -> None:
    """Shut down the active plugin. Never raises."""
    if _registry is not None:
        await _registry.shutdown_all()


def get_swap_item_service() -> SwapItemService:
    """
    FastAPI dependency — injected via Depends(get_swap_item_service).

    Both backends register under capability="persistence", so the lookup
    is always the same regardless of which plugin is active.
    """
    if _registry is None:
        raise RuntimeError("PluginRegistry not initialised.")

    repo = TracingProxy(
        _registry.get("persistence").get_repository(),
        prefix="repository.swap_item",
    )
    return SwapItemService(repo)
