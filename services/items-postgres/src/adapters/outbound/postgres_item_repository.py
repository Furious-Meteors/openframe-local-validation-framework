from datetime import datetime, timezone
from typing import List, Optional

import asyncpg

from domain.item import Item


class PostgresItemRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, item: Item) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO items (id, name, description, status, created_at)
                VALUES ($1, $2, $3, $4, NOW())
                ON CONFLICT (id) DO UPDATE
                SET name        = EXCLUDED.name,
                    description = EXCLUDED.description,
                    status      = EXCLUDED.status
                """,
                item.id, item.name, item.description, item.status,
            )

    async def get(self, item_id: str) -> Optional[Item]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, description, status, created_at FROM items WHERE id = $1",
                item_id,
            )
        if row is None:
            return None
        return Item(**dict(row))

    async def list(self, status: Optional[str] = None) -> List[Item]:
        async with self._pool.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    "SELECT id, name, description, status, created_at"
                    " FROM items WHERE status = $1",
                    status,
                )
            else:
                rows = await conn.fetch(
                    "SELECT id, name, description, status, created_at FROM items"
                )
        return [Item(**dict(r)) for r in rows]

    async def bulk_save(self, items: List[Item]) -> None:
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.copy_records_to_table(
                "items",
                records=[
                    (i.id, i.name, i.description, i.status, now) for i in items
                ],
                columns=["id", "name", "description", "status", "created_at"],
            )

    async def delete(self, item_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM items WHERE id = $1", item_id
            )
        return result != "DELETE 0"
