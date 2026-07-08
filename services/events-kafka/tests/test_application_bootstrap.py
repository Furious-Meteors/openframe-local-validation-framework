"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks the plugin backend (KafkaPlugin's initialize()/shutdown()), not
ApplicationBootstrap itself, so the real configure()/start()/stop() control
flow defined in openframe-core actually runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.queue.kafka import KafkaPlugin
from openframe.core.ports           import Capability
from openframe.core.runtime         import ApplicationBootstrap

from src.bootstrap.app import EventsKafkaApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    monkeypatch.setattr(KafkaPlugin, "initialize", AsyncMock())
    monkeypatch.setattr(KafkaPlugin, "shutdown", AsyncMock())


@pytest.fixture
def app() -> EventsKafkaApp:
    return EventsKafkaApp()


def test_events_kafka_app_is_application_bootstrap_instance(app):
    assert isinstance(app, ApplicationBootstrap)


def test_dependencies_app_instance_is_events_kafka_app():
    from src.bootstrap.dependencies import _app
    assert isinstance(_app, EventsKafkaApp)


def test_configure_registers_one_plugin(app):
    app.configure()
    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-kafka"]


def test_capabilities_registered_after_configure(app):
    app.configure()
    assert app.get(Capability.QUEUE).capability == Capability.QUEUE


async def test_start_calls_configure_and_initialize_all(app):
    assert app._registry.list_plugins() == []

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-kafka"]
    KafkaPlugin.initialize.assert_awaited_once()


async def test_stop_calls_shutdown_all_and_shutdown_telemetry(app, monkeypatch):
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    await app.start()
    await app.stop()

    KafkaPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1


async def test_make_consumer_returns_fresh_instance_each_call(app, monkeypatch):
    """
    dependencies.make_consumer() constructs OrderEventConsumer directly
    (not via KafkaPlugin.make_consumer(), which loses the _deserialise()
    override) — lock in that each call returns a distinct instance.
    """
    await app.start()
    from src.bootstrap import dependencies
    monkeypatch.setattr(dependencies, "_app", app)

    c1 = dependencies.make_consumer()
    c2 = dependencies.make_consumer()

    from src.adapters.outbound.order_consumer import OrderEventConsumer
    assert isinstance(c1, OrderEventConsumer)
    assert c1 is not c2
