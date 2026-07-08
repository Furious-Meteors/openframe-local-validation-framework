"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks the plugin backend (RedisPlugin's initialize()/shutdown()), not
ApplicationBootstrap itself, so the real configure()/start()/stop() control
flow defined in openframe-core actually runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.db.redis import RedisPlugin
from openframe.core.ports        import Capability
from openframe.core.runtime      import ApplicationBootstrap

from src.bootstrap.app import CacheRedisApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    monkeypatch.setattr(RedisPlugin, "initialize", AsyncMock())
    monkeypatch.setattr(RedisPlugin, "shutdown", AsyncMock())


@pytest.fixture
def app() -> CacheRedisApp:
    return CacheRedisApp()


def test_cache_redis_app_is_application_bootstrap_instance(app):
    assert isinstance(app, ApplicationBootstrap)


def test_dependencies_app_instance_is_cache_redis_app():
    from src.bootstrap.dependencies import _app
    assert isinstance(_app, CacheRedisApp)


def test_configure_registers_one_plugin(app):
    app.configure()
    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-redis"]


def test_capabilities_registered_after_configure(app):
    app.configure()
    assert app.get(Capability.CACHE).capability == Capability.CACHE


async def test_start_calls_configure_and_initialize_all(app):
    assert app._registry.list_plugins() == []

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-redis"]
    RedisPlugin.initialize.assert_awaited_once()


async def test_stop_calls_shutdown_all_and_shutdown_telemetry(app, monkeypatch):
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    await app.start()
    await app.stop()

    RedisPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1
