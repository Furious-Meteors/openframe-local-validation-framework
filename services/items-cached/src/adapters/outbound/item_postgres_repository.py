"""PostgreSQL adapter for item persistence."""
from __future__ import annotations

from typing import Any

import asyncpg

from openframe.adapters.db.postgres import PostgresRepository
from src.domain.item import Item


class ItemPostgresRepository(PostgresRepository[Item]):
    _table     = "items"
    _id_column = "id"

    def _row_to_entity(self, row: asyncpg.Record) -> Item:
        return Item(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=row["status"],
            created_at=row.get("created_at"),
        )

    def _entity_to_row(self, entity: Item) -> dict[str, Any]:
        return {
            "id":          entity.id,
            "name":        entity.name,
            "description": entity.description,
            "status":      entity.status,
        }
