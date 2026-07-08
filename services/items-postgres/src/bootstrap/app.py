"""
ApplicationBootstrap composition root — Stage 1 wiring, single adapter.

This is the ONLY file that imports from openframe.adapters and
openframe.core.runtime. bootstrap/dependencies.py reads the registered
port through _app.get(Capability.PERSISTENCE) instead of owning the
plugin directly.
"""
from __future__ import annotations

from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
from openframe.core.runtime import ApplicationBootstrap

from src.adapters.outbound.item_repository import ItemPostgresRepository


class ItemsPostgresApp(ApplicationBootstrap):
    """ApplicationBootstrap subclass wiring a single PostgresPlugin."""

    def configure(self) -> None:
        """Register the Postgres persistence plugin."""
        # repository_class ensures get_repository() returns ItemPostgresRepository,
        # not the plain base PostgresRepository. Without this, _row_to_entity()/
        # _entity_to_row() overrides are silently discarded.
        self.register(PostgresPlugin(
            PostgresSettings(),
            table="items",
            id_column="id",
            repository_class=ItemPostgresRepository,
        ))
