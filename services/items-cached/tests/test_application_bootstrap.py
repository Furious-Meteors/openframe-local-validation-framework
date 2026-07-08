"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks the plugin backends (PostgresPlugin/RedisPlugin's initialize()/
shutdown()), not ApplicationBootstrap itself — the same approach used in
test_plugin_wiring.py — so the real configure()/start()/stop() control flow
defined in openframe-core actually runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.db.postgres import PostgresPlugin
from openframe.adapters.db.redis    import RedisPlugin
from openframe.core.ports           import Capability
from openframe.core.runtime         import ApplicationBootstrap

from src.bootstrap.app import ItemsCachedApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    for cls in (PostgresPlugin, RedisPlugin):
        monkeypatch.setattr(cls, "initialize", AsyncMock())
        monkeypatch.setattr(cls, "shutdown", AsyncMock())


@pytest.fixture
def app() -> ItemsCachedApp:
    return ItemsCachedApp()


# ── type / identity ───────────────────────────────────────────────────────────

def test_items_cached_app_is_application_bootstrap_instance(app):
    assert isinstance(app, ApplicationBootstrap)


def test_dependencies_app_instance_is_items_cached_app():
    from src.bootstrap.dependencies import _app
    assert isinstance(_app, ItemsCachedApp)


# ── configure() ────────────────────────────────────────────────────────────────

def test_configure_registers_two_plugins_in_correct_order(app):
    app.configure()
    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres", "openframe-redis"], (
        "Registration order must be Postgres -> Redis: persistence must "
        "be ready before caching."
    )


def test_capabilities_registered_after_configure(app):
    app.configure()
    assert app.get(Capability.PERSISTENCE).capability == Capability.PERSISTENCE
    assert app.get(Capability.CACHE).capability == Capability.CACHE


# ── start() ───────────────────────────────────────────────────────────────────

async def test_start_calls_configure_and_initialize_all(app):
    assert app._registry.list_plugins() == []

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres", "openframe-redis"]
    PostgresPlugin.initialize.assert_awaited_once()
    RedisPlugin.initialize.assert_awaited_once()


# ── stop() ────────────────────────────────────────────────────────────────────

async def test_stop_calls_shutdown_all_and_shutdown_telemetry(app, monkeypatch):
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    await app.start()
    await app.stop()

    PostgresPlugin.shutdown.assert_awaited_once()
    RedisPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1
