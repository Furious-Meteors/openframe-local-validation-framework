"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks the plugin backend (PostgresPlugin's initialize()/shutdown()), not
ApplicationBootstrap itself, so the real configure()/start()/stop() control
flow defined in openframe-core actually runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.db.postgres import PostgresPlugin
from openframe.core.ports          import Capability
from openframe.core.runtime        import ApplicationBootstrap

from src.bootstrap.app import ItemsPostgresApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    """
    Patch initialize()/shutdown() on PostgresPlugin so configure() -> start()
    -> stop() never touches a real Postgres backend. Settings() construction
    still runs for real — pure env parsing, satisfied by the autouse
    _test_env fixture in conftest.py.
    """
    monkeypatch.setattr(PostgresPlugin, "initialize", AsyncMock())
    monkeypatch.setattr(PostgresPlugin, "shutdown", AsyncMock())


@pytest.fixture
def app() -> ItemsPostgresApp:
    return ItemsPostgresApp()


# ── type / identity ───────────────────────────────────────────────────────────

def test_items_postgres_app_is_application_bootstrap_instance(app):
    assert isinstance(app, ApplicationBootstrap)


def test_dependencies_app_instance_is_items_postgres_app():
    from src.bootstrap.dependencies import _app
    assert isinstance(_app, ItemsPostgresApp)


# ── configure() ────────────────────────────────────────────────────────────────

def test_configure_registers_one_plugin(app):
    app.configure()
    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres"]


def test_capabilities_registered_after_configure(app):
    app.configure()
    assert app.get(Capability.PERSISTENCE).capability == Capability.PERSISTENCE


# ── start() ───────────────────────────────────────────────────────────────────

async def test_start_calls_configure_and_initialize_all(app):
    assert app._registry.list_plugins() == []  # nothing registered before start()

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres"], (
        "start() must call configure() to register the plugin."
    )
    PostgresPlugin.initialize.assert_awaited_once()


# ── stop() ────────────────────────────────────────────────────────────────────

async def test_stop_calls_shutdown_all_and_shutdown_telemetry(app, monkeypatch):
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    await app.start()
    await app.stop()

    PostgresPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1
