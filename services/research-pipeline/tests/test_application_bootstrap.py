"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks the plugin backends (MongoPlugin/RedisPlugin/KafkaPlugin's initialize()/
shutdown()), not ApplicationBootstrap itself — the same approach used in
test_plugin_wiring.py — so the real configure()/start()/stop() control flow
defined in openframe-core actually runs.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.db.mongo    import MongoPlugin
from openframe.adapters.db.redis    import RedisPlugin
from openframe.adapters.queue.kafka import KafkaPlugin
from openframe.core.ports           import Capability
from openframe.core.runtime         import ApplicationBootstrap

from src.bootstrap.app import ResearchPipelineApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    """
    Patch initialize()/shutdown() on the plugin classes so configure() ->
    start() -> stop() never touches a real Mongo/Redis/Kafka backend.
    Settings() construction still runs for real — it's pure env parsing,
    already satisfied by the autouse _test_env fixture in conftest.py.
    """
    for cls in (MongoPlugin, RedisPlugin, KafkaPlugin):
        monkeypatch.setattr(cls, "initialize", AsyncMock())
        monkeypatch.setattr(cls, "shutdown", AsyncMock())


@pytest.fixture
def app() -> ResearchPipelineApp:
    return ResearchPipelineApp()


# ── type / identity ───────────────────────────────────────────────────────────

def test_research_pipeline_app_is_application_bootstrap_instance(app):
    assert isinstance(app, ApplicationBootstrap)


def test_dependencies_app_instance_is_research_pipeline_app():
    from src.bootstrap.dependencies import _app
    assert isinstance(_app, ResearchPipelineApp)


# ── configure() ────────────────────────────────────────────────────────────────

def test_configure_registers_three_plugins_in_correct_order(app):
    app.configure()
    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-mongo", "openframe-redis", "openframe-kafka"], (
        "Registration order must be Mongo -> Redis -> Kafka: persistence must "
        "be ready before caching, caching before events."
    )


def test_capabilities_registered_after_configure(app):
    app.configure()
    assert app.get(Capability.PERSISTENCE).capability == Capability.PERSISTENCE
    assert app.get(Capability.CACHE).capability == Capability.CACHE
    assert app.get(Capability.QUEUE).capability == Capability.QUEUE


# ── start() ───────────────────────────────────────────────────────────────────

async def test_start_calls_configure_and_initialize_all(app):
    assert app._registry.list_plugins() == []  # nothing registered before start()

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-mongo", "openframe-redis", "openframe-kafka"], (
        "start() must call configure() to register the three plugins."
    )
    MongoPlugin.initialize.assert_awaited_once()
    RedisPlugin.initialize.assert_awaited_once()
    KafkaPlugin.initialize.assert_awaited_once()


# ── stop() ────────────────────────────────────────────────────────────────────

async def test_stop_calls_shutdown_all_and_shutdown_telemetry(app, monkeypatch):
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    await app.start()
    await app.stop()

    MongoPlugin.shutdown.assert_awaited_once()
    RedisPlugin.shutdown.assert_awaited_once()
    KafkaPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1


async def test_stop_cancels_background_consumer_task(app):
    async def _never_returns():
        await asyncio.sleep(3600)

    await app.start()
    await app.start_consumer(_never_returns)
    assert app._consumer_task is not None
    assert not app._consumer_task.done()

    await app.stop()

    assert app._consumer_task is None
