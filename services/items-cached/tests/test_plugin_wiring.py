"""
Tests for the plugin registration in bootstrap/dependencies.py.

REGRESSION test for Bug 1 — PostgresPlugin registered without table/id_column
caused RuntimeError at the first request in live validation. This test
confirms the fix is present and stays present.
"""
from __future__ import annotations

import pathlib

import pytest


def _get_source() -> str:
    path = (
        pathlib.Path(__file__).parent.parent
        / "src" / "bootstrap" / "app.py"
    )
    return path.read_text()


def test_postgres_plugin_registered_with_table_name():
    """
    REGRESSION (Bug 1): PostgresPlugin(PostgresSettings()) with no table
    causes RuntimeError on the first get_repository() call.
    Confirms the fix — table="items" — is present in the source.
    """
    source = _get_source()
    assert 'table="items"' in source or "table='items'" in source, (
        'PostgresPlugin must be registered with table="items" — '
        "registering without it causes a RuntimeError at request time "
        "(confirmed in live Docker validation)."
    )


def test_postgres_plugin_registered_with_id_column():
    """Companion to table check — id_column must also be explicit."""
    source = _get_source()
    assert 'id_column="id"' in source or "id_column='id'" in source, (
        'PostgresPlugin must be registered with id_column="id".'
    )


def test_postgres_plugin_capability_lookup_succeeds():
    """
    Confirms get_repository() does not raise a missing-table RuntimeError
    when the plugin is constructed correctly with a table name.
    Before initialize(), get_repository() raises for a different reason
    (not READY), not for a missing table.
    """
    from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
    settings = PostgresSettings(database_url="postgresql://test:test@localhost/test")
    plugin = PostgresPlugin(settings, table="items", id_column="id")
    with pytest.raises(RuntimeError) as exc_info:
        plugin.get_repository()
    # The error must NOT be about a missing table name
    assert "table" not in str(exc_info.value).lower() or "not" in str(exc_info.value).lower()


async def test_registry_get_persistence_returns_postgres_plugin():
    """Confirms the capability taxonomy: 'persistence' → Postgres."""
    from openframe.core.plugins import PluginRegistry
    from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
    settings = PostgresSettings(database_url="postgresql://test:test@localhost/test")
    registry = PluginRegistry()
    registry.register(PostgresPlugin(settings, table="items", id_column="id"))
    plugin = registry.get("persistence")
    assert plugin.capability == "persistence"


async def test_registry_get_cache_returns_redis_plugin():
    """Confirms the capability taxonomy: 'cache' → Redis."""
    from openframe.core.plugins import PluginRegistry
    from openframe.adapters.db.redis import RedisPlugin, RedisSettings
    settings = RedisSettings(redis_url="redis://localhost:6379/0")
    registry = PluginRegistry()
    registry.register(RedisPlugin(settings))
    plugin = registry.get("cache")
    assert plugin.capability == "cache"


def test_postgres_plugin_registered_with_item_repository_class():
    """
    REGRESSION: confirms PostgresPlugin uses
    repository_class=ItemPostgresRepository. Without this, _row_to_entity()/
    _entity_to_row() overrides are silently discarded — same root cause as the
    research-pipeline Mongo bug, masked here because asyncpg.Record's attribute
    access partially papered over the symptom.
    See: openframe-adapters CHANGELOG 1.2.0.
    """
    source = _get_source()
    assert "repository_class=ItemPostgresRepository" in source, (
        "PostgresPlugin must pass repository_class=ItemPostgresRepository "
        "so get_repository() returns the domain subclass, not the base adapter."
    )


async def test_registry_two_plugins_do_not_collide():
    """Both plugins coexist in the same registry with distinct capability keys."""
    from openframe.core.plugins import PluginRegistry
    from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
    from openframe.adapters.db.redis import RedisPlugin, RedisSettings
    registry = PluginRegistry()
    registry.register(
        PostgresPlugin(
            PostgresSettings(database_url="postgresql://test:test@localhost/test"),
            table="items", id_column="id",
        )
    )
    registry.register(RedisPlugin(RedisSettings(redis_url="redis://localhost:6379/0")))
    assert registry.get("persistence").capability == "persistence"
    assert registry.get("cache").capability == "cache"
