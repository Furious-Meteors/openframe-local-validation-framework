"""
Composition root — Stage 1 wiring, ApplicationBootstrap.

This is the FastAPI dependency layer. Together with
:class:`~src.bootstrap.app.ArtifactsMongoApp` (ApplicationBootstrap, which
owns the actual plugin registration in its configure()), ``bootstrap/`` is
the only package that imports from openframe.adapters. This module provides
``Depends()``-friendly functions that read from the module-level ``_app``
instance instead of owning the port directly.
"""
from __future__ import annotations

from openframe.core.ports   import Capability
from openframe.core.tracing import TracingProxy

from src.application.services.artifact_service import ArtifactService
from src.bootstrap.app import ArtifactsMongoApp

_app: ArtifactsMongoApp = ArtifactsMongoApp()


async def initialise() -> None:
    """
    Configure and initialise the Mongo plugin.

    Called once per FastAPI lifespan startup. Rebuilds ``_app`` fresh each
    call so repeated startup/shutdown cycles never re-register a plugin
    into an already-populated registry.
    """
    global _app
    _app = ArtifactsMongoApp()
    await _app.start()


async def shutdown() -> None:
    """Shut down the plugin and flush telemetry. Never raises."""
    await _app.stop()


def get_artifact_service() -> ArtifactService:
    """FastAPI dependency — call via Depends(get_artifact_service)."""
    traced = TracingProxy(
        _app.get(Capability.PERSISTENCE).get_repository(),
        prefix="repository.artifact",
    )
    return ArtifactService(traced)
