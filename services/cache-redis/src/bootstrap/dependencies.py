"""
Composition root — Stage 1 wiring, ApplicationBootstrap.

This is the FastAPI dependency layer. Together with
:class:`~src.bootstrap.app.CacheRedisApp` (ApplicationBootstrap, which owns
plugin registration in its configure()), ``bootstrap/`` is the only package
that imports from openframe.adapters. This module provides
``Depends()``-friendly functions that read from the module-level ``_app``
instance instead of owning the port directly.
"""
from __future__ import annotations

from openframe.core.tracing import TracingProxy

from src.adapters.outbound.session_repository import SessionRedisRepository
from src.application.services.session_service import SessionService
from src.bootstrap.app import CacheRedisApp

_app: CacheRedisApp = CacheRedisApp()


async def initialise() -> None:
    """
    Configure and initialise the Redis plugin.

    Called once per FastAPI lifespan startup. Rebuilds ``_app`` fresh each
    call so repeated startup/shutdown cycles never re-register a plugin
    into an already-populated registry.
    """
    global _app
    _app = CacheRedisApp()
    await _app.start()


async def shutdown() -> None:
    """Shut down the plugin and flush telemetry. Never raises."""
    await _app.stop()


def get_session_service() -> SessionService:
    """
    FastAPI dependency — call via Depends(get_session_service).

    RedisPlugin.get_repository() would return the base RedisRepository — it
    has no repository_class= support, so extend_ttl()/get_stats() and the
    Session dict-mapping overrides would be silently missing. Construct
    SessionRedisRepository directly against the plugin's own settings
    instead; RedisPlugin is still registered via ApplicationBootstrap for
    its initialize()/shutdown()/health() lifecycle, and the connection pool
    is shared (openframe's redis client cache is keyed by redis_url).
    """
    repo = SessionRedisRepository(_app.settings)
    traced = TracingProxy(repo, prefix="cache.session")
    return SessionService(traced)
