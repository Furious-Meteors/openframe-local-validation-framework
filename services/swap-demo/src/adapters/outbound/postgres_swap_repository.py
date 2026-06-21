"""
PostgreSQL adapter for swap-demo persistence.

Extends PostgresRepository[SwapItem] from openframe-adapters-db-postgres.
Inherits full CRUD (get, list, create, update, delete, ping, is_ready).
Adds save() — an UPSERT operation not in BaseRepository — using the
publicly exported get_postgres_pool() helper.
"""
from __future__ import annotations

from typing import Any

import asyncpg

from openframe.adapters.db.postgres import PostgresRepository, get_postgres_pool

from domain.swap_item import SwapItem


class PostgresSwapRepository(PostgresRepository[SwapItem]):
    _table     = "swap_items"
    _id_column = "id"

    def _row_to_entity(self, row: asyncpg.Record) -> SwapItem:
        return SwapItem(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            created_at=row.get("created_at"),
        )

    def _entity_to_row(self, entity: SwapItem) -> dict[str, Any]:
        return {
            "id":          entity.id,
            "name":        entity.name,
            "description": entity.description,
        }

    async def save(self, item: SwapItem) -> None:
        """
        Upsert — insert or update in one statement.

        Domain-specific operation not in BaseRepository.
        Uses get_postgres_pool() rather than re-opening a connection,
        so the adapter participates in the same pool managed by PostgresPlugin.
        """
        pool = await get_postgres_pool(self._settings)
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO swap_items (id, name, description, created_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (id) DO UPDATE
                SET name        = EXCLUDED.name,
                    description = EXCLUDED.description
                """,
                item.id, item.name, item.description,
            )
