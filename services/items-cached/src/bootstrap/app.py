"""
ApplicationBootstrap composition root — Stage 2 wiring with TWO adapters.

This is the ONLY file that imports from openframe.adapters and
openframe.core.runtime. bootstrap/dependencies.py reads the registered
ports through _app.get(Capability.X) instead of owning the registry
directly.

Registration order (= initialisation order):
    1. PostgresPlugin — capability="persistence" — items must be persisted
                          before caching
    2. RedisPlugin    — capability="cache"       — cache layer depends on
                          persistence being available

Shutdown order (LIFO — reverse of registration, handled by
ApplicationBootstrap.stop()):
    1. RedisPlugin    — flush cache
    2. PostgresPlugin — close connections last
    3. shutdown_telemetry() — flush OTel SDK last of all
"""
from __future__ import annotations

from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
from openframe.adapters.db.redis    import RedisPlugin, RedisSettings
from openframe.core.runtime         import ApplicationBootstrap

from src.adapters.outbound.item_postgres_repository import ItemPostgresRepository


class ItemsCachedApp(ApplicationBootstrap):
    """ApplicationBootstrap subclass wiring Postgres + Redis."""

    def configure(self) -> None:
        """Register both plugins in the order persistence -> cache."""
        # repository_class ensures get_repository() returns ItemPostgresRepository,
        # not the plain base PostgresRepository. Without this, _row_to_entity()/
        # _entity_to_row() overrides are silently discarded.
        self.register(PostgresPlugin(
            PostgresSettings(),
            table="items",
            id_column="id",
            repository_class=ItemPostgresRepository,
        ))

        # Redis second — cache layer depends on persistence being available.
        # RedisPlugin has no repository_class= parameter (unlike Postgres/
        # Mongo/Kafka), so get_repository() always returns the plain base
        # RedisRepository rather than ItemRedisRepository — this matches the
        # pre-ApplicationBootstrap behaviour exactly (same gap existed with
        # the raw PluginRegistry wiring this replaces).
        self.register(RedisPlugin(RedisSettings()))
