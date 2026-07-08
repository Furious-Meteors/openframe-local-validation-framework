"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks both plugin backends' initialize()/shutdown() so the real
configure()/start()/stop() control flow defined in openframe-core actually
runs, and proves configure() registers exactly one plugin — gated by
PERSISTENCE_BACKEND — never both.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.db.mongo    import MongoPlugin
from openframe.adapters.db.postgres import PostgresPlugin
from openframe.core.ports           import Capability
from openframe.core.runtime         import ApplicationBootstrap

from bootstrap.app import SwapDemoApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    for cls in (PostgresPlugin, MongoPlugin):
        monkeypatch.setattr(cls, "initialize", AsyncMock())
        monkeypatch.setattr(cls, "shutdown", AsyncMock())


def test_swap_demo_app_is_application_bootstrap_instance():
    assert isinstance(SwapDemoApp(), ApplicationBootstrap)


def test_dependencies_app_instance_is_swap_demo_app():
    from bootstrap.dependencies import _app
    assert isinstance(_app, SwapDemoApp)


# ── conditional registration ────────────────────────────────────────────────

def test_configure_registers_postgres_when_backend_unset(monkeypatch):
    monkeypatch.delenv("PERSISTENCE_BACKEND", raising=False)
    app = SwapDemoApp()
    app.configure()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres"]
    assert app.get(Capability.PERSISTENCE).capability == Capability.PERSISTENCE


def test_configure_registers_postgres_when_backend_explicitly_postgres(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    app = SwapDemoApp()
    app.configure()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres"]


def test_configure_registers_mongo_when_backend_env_mongo(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "mongo")
    app = SwapDemoApp()
    app.configure()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-mongo"]
    assert app.get(Capability.PERSISTENCE).capability == Capability.PERSISTENCE


def test_backend_read_at_construction_not_module_import(monkeypatch):
    """
    self._backend must reflect PERSISTENCE_BACKEND at SwapDemoApp()
    construction time, so tests (and repeated lifespan startups) that
    change the env between instances are honoured correctly.
    """
    monkeypatch.setenv("PERSISTENCE_BACKEND", "mongo")
    mongo_app = SwapDemoApp()
    assert mongo_app._backend == "mongo"

    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    postgres_app = SwapDemoApp()
    assert postgres_app._backend == "postgres"


# ── start()/stop() ───────────────────────────────────────────────────────────

async def test_start_calls_configure_and_initialize_all(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    app = SwapDemoApp()
    assert app._registry.list_plugins() == []

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-postgres"]
    PostgresPlugin.initialize.assert_awaited_once()
    MongoPlugin.initialize.assert_not_awaited()


async def test_stop_calls_shutdown_all_and_shutdown_telemetry(monkeypatch):
    monkeypatch.setenv("PERSISTENCE_BACKEND", "postgres")
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    app = SwapDemoApp()
    await app.start()
    await app.stop()

    PostgresPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1
