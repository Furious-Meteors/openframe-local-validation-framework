"""
PostgreSQL adapter for item persistence.

Subclasses PostgresRepository[Item] from openframe-adapters.
Provides domain mapping (_row_to_entity, _entity_to_row).
Adds domain-specific queries using raw asyncpg.

This is the ONLY file in the service that imports from openframe.adapters.
"""
from __future__ import annotations

from typing import Any

import asyncpg

from openframe.adapters.db.postgres import PostgresRepository, get_postgres_pool

from src.domain.item import Item


class ItemPostgresRepository(PostgresRepository[Item]):
    """
    Item repository backed by PostgreSQL.

    Inherits full CRUD from PostgresRepository[Item]:
        get(), list(), create(), update(), delete(),
        ping(), is_ready(), close()

    Adds domain-specific operations:
        find_by_status() — filtered query via raw asyncpg
        bulk_import()    — asyncpg COPY protocol, 10x faster than INSERT
    """

    _table = "items"
    _id_column = "id"

    def _row_to_entity(self, row: asyncpg.Record) -> Item:
        """Convert asyncpg.Record to Item domain object."""
        return Item(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=row["status"],
            created_at=row.get("created_at"),
        )

    def _entity_to_row(self, entity: Item) -> dict[str, Any]:
        """Convert Item domain object to dict for SQL INSERT/UPDATE."""
        return {
            "id": entity.id,
            "name": entity.name,
            "description": entity.description,
            "status": entity.status,
        }

    # ── Niche feature 1: Raw asyncpg filtered query ───────────────────────
    # Not in BaseRepository. Arbitrary SQL with full asyncpg parameterisation.

    async def find_by_status(self, status: str) -> list[Item]:
        """
        Find all items with a specific status.

        Uses raw asyncpg directly — no abstraction needed.
        The adapter gets out of the way.
        """
        pool = await get_postgres_pool(self._settings)
        rows = await pool.fetch(
            "SELECT * FROM items WHERE status = $1 ORDER BY name",
            status,
        )
        return [self._row_to_entity(r) for r in rows]

    # ── Niche feature 2: asyncpg COPY protocol ────────────────────────────
    # Not in BaseRepository. 10x faster than individual INSERTs for bulk data.

    async def bulk_import(self, items: list[Item]) -> int:
        """
        Bulk insert using asyncpg COPY protocol.

        asyncpg is the fastest possible way to insert many rows.
        Individual INSERTs are ~10x slower for the same data volume.
        """
        pool = await get_postgres_pool(self._settings)
        async with pool.acquire() as conn:
            await conn.copy_records_to_table(
                "items",
                records=[
                    (i.id, i.name, i.description, i.status)
                    for i in items
                ],
                columns=["id", "name", "description", "status"],
            )
        return len(items)
