"""
Composition root — Stage 1 wiring, ApplicationBootstrap.

This is the FastAPI dependency layer. Together with
:class:`~src.bootstrap.app.EventsKafkaApp` (ApplicationBootstrap, which owns
plugin registration in its configure()), ``bootstrap/`` is the only package
that imports from openframe.adapters. This module provides
``Depends()``-friendly functions that read from the module-level ``_app``
instance instead of owning the port directly.

Producer is long-lived (started via KafkaPlugin.initialize() during
_app.start()). Consumer is created fresh per subscribe() session via
make_consumer() — constructed directly against the app's settings rather
than through the plugin's own make_consumer() (see app.py's module
docstring for why). No app-level start_consumer()/stop_consumer() override
is needed here since the background asyncio.Task lifecycle is owned by
main.py's lifespan, not this app (unlike research-pipeline's single
long-lived background consumer).
"""
from __future__ import annotations

from openframe.core.ports   import Capability
from openframe.core.tracing import TracingProxy

from src.adapters.outbound.order_consumer import OrderEventConsumer
from src.application.services.event_service import EventService
from src.bootstrap.app import EventsKafkaApp

_app: EventsKafkaApp = EventsKafkaApp()


async def initialise() -> None:
    """
    Configure and initialise the Kafka plugin.

    Called once per FastAPI lifespan startup. Rebuilds ``_app`` fresh each
    call so repeated startup/shutdown cycles never re-register a plugin
    into an already-populated registry.
    """
    global _app
    _app = EventsKafkaApp()
    await _app.start()


async def shutdown() -> None:
    """Shut down the plugin and flush telemetry. Never raises."""
    await _app.stop()


def get_event_service() -> EventService:
    """FastAPI dependency — call via Depends(get_event_service)."""
    traced = TracingProxy(
        _app.get(Capability.QUEUE).get_producer(),
        prefix="queue.event",
    )
    return EventService(traced)


def make_consumer() -> OrderEventConsumer:
    """
    Create a fresh consumer for a subscribe session.

    Constructed directly rather than via _app.get(Capability.QUEUE).make_consumer()
    — the plugin's make_consumer() always returns the plain base KafkaConsumer,
    which would silently lose OrderEventConsumer's _deserialise() override.
    """
    return OrderEventConsumer(_app.settings)
