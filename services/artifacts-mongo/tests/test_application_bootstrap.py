"""
Tests for the ApplicationBootstrap migration (bootstrap/app.py + dependencies.py).

Mocks the plugin backend (MongoPlugin's initialize()/shutdown()), not
ApplicationBootstrap itself, so the real configure()/start()/stop() control
flow defined in openframe-core actually runs.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from openframe.adapters.db.mongo import MongoPlugin
from openframe.core.ports        import Capability
from openframe.core.runtime      import ApplicationBootstrap

from src.bootstrap.app import ArtifactsMongoApp


@pytest.fixture(autouse=True)
def _mock_plugin_lifecycle(monkeypatch):
    monkeypatch.setattr(MongoPlugin, "initialize", AsyncMock())
    monkeypatch.setattr(MongoPlugin, "shutdown", AsyncMock())


@pytest.fixture
def app() -> ArtifactsMongoApp:
    return ArtifactsMongoApp()


def test_artifacts_mongo_app_is_application_bootstrap_instance(app):
    assert isinstance(app, ApplicationBootstrap)


def test_dependencies_app_instance_is_artifacts_mongo_app():
    from src.bootstrap.dependencies import _app
    assert isinstance(_app, ArtifactsMongoApp)


def test_configure_registers_one_plugin(app):
    app.configure()
    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-mongo"]


def test_capabilities_registered_after_configure(app):
    app.configure()
    assert app.get(Capability.PERSISTENCE).capability == Capability.PERSISTENCE


async def test_start_calls_configure_and_initialize_all(app):
    assert app._registry.list_plugins() == []

    await app.start()

    names = [p.message for p in app._registry.list_plugins()]
    assert names == ["openframe-mongo"]
    MongoPlugin.initialize.assert_awaited_once()


async def test_stop_calls_shutdown_all_and_shutdown_telemetry(app, monkeypatch):
    mock_shutdown_telemetry = MagicMock()
    monkeypatch.setattr(
        "openframe.core.telemetry.shutdown_telemetry", mock_shutdown_telemetry
    )

    await app.start()
    await app.stop()

    MongoPlugin.shutdown.assert_awaited_once()
    assert mock_shutdown_telemetry.call_count >= 1
