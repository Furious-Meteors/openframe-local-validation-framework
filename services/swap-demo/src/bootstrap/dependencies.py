"""
Composition root — Stage 1 wiring with adapter swap, ApplicationBootstrap.

This is the FastAPI dependency layer. Together with
:class:`~bootstrap.app.SwapDemoApp` (ApplicationBootstrap, which owns the
conditional plugin registration in its configure()), ``bootstrap/`` is the
only package that imports from openframe.adapters. This module provides
``Depends()``-friendly functions that read from the module-level ``_app``
instance instead of owning the registry directly.

Function names (init_backends/close_backends) are kept as-is rather than
renamed to initialise()/shutdown() — entrypoints/http/main.py already
imports these names and there's no reason to churn it during this migration.
"""
from __future__ import annotations

from openframe.core.ports   import Capability
from openframe.core.tracing import TracingProxy

from application.services.swap_item_service import SwapItemService
from bootstrap.app import SwapDemoApp

_app: SwapDemoApp = SwapDemoApp()


async def init_backends() -> None:
    """
    Register and initialise the active backend plugin.

    Called once in FastAPI lifespan on startup. Rebuilds ``_app`` fresh
    each call so repeated startup/shutdown cycles never re-register a
    plugin into an already-populated registry.
    """
    global _app
    _app = SwapDemoApp()
    await _app.start()


async def close_backends() -> None:
    """Shut down the active plugin and flush telemetry. Never raises."""
    await _app.stop()


def get_swap_item_service() -> SwapItemService:
    """
    FastAPI dependency — injected via Depends(get_swap_item_service).

    Both backends register under Capability.PERSISTENCE, so the lookup is
    always the same regardless of which plugin is active.
    """
    repo = TracingProxy(
        _app.get(Capability.PERSISTENCE).get_repository(),
        prefix="repository.swap_item",
    )
    return SwapItemService(repo)
