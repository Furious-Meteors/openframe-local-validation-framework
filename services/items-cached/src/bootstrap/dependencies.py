"""
Composition root — Stage 2 wiring, ApplicationBootstrap.

This is the FastAPI dependency layer. Together with
:class:`~src.bootstrap.app.ItemsCachedApp` (ApplicationBootstrap, which owns
plugin registration in its configure()), ``bootstrap/`` is the only package
that imports from openframe.adapters. This module provides
``Depends()``-friendly functions that read from the module-level ``_app``
instance instead of owning the registry directly.

Capability taxonomy:
    Capability.PERSISTENCE → PostgresPlugin → ItemPostgresRepository
    Capability.CACHE       → RedisPlugin   → ItemRedisRepository (base class — see app.py)
"""
from __future__ import annotations

from openframe.core.ports   import Capability
from openframe.core.tracing import TracingProxy

from src.application.services.item_service import ItemCachedService
from src.bootstrap.app import ItemsCachedApp

_app: ItemsCachedApp = ItemsCachedApp()


async def initialise() -> None:
    """
    Configure and initialise both plugins.

    Called once per FastAPI lifespan startup. Rebuilds ``_app`` fresh each
    call so repeated startup/shutdown cycles never re-register plugins
    into an already-populated registry.
    """
    global _app
    _app = ItemsCachedApp()
    await _app.start()


async def shutdown() -> None:
    """Shut down both plugins (LIFO) and flush telemetry. Never raises."""
    await _app.stop()


async def health_all() -> dict:
    """Aggregate health across both plugins."""
    return await _app.health()


def list_plugins():
    """Registered plugin snapshots — used by the /registry debug endpoint."""
    return _app._registry.list_plugins()


def get_item_service() -> ItemCachedService:
    """
    FastAPI dependency — injected via Depends(get_item_service).

    Span prefixes:
        repository.item.postgres — Postgres spans
        cache.item.redis         — Redis spans
    """
    persistence = TracingProxy(
        _app.get(Capability.PERSISTENCE).get_repository(),
        prefix="repository.item.postgres",
    )
    cache = TracingProxy(
        _app.get(Capability.CACHE).get_repository(),
        prefix="cache.item.redis",
    )

    return ItemCachedService(persistence=persistence, cache=cache)
