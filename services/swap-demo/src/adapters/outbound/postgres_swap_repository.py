from typing import List, Optional

import asyncpg

from domain.swap_item import SwapItem


class PostgresSwapRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, item: SwapItem) -> None:
        async with self._pool.acquire() as conn:
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

    async def get(self, item_id: str) -> Optional[SwapItem]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, description, created_at FROM swap_items WHERE id = $1",
                item_id,
            )
        if row is None:
            return None
        return SwapItem(**dict(row))

    async def list(self) -> List[SwapItem]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, description, created_at FROM swap_items"
            )
        return [SwapItem(**dict(r)) for r in rows]

    async def delete(self, item_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM swap_items WHERE id = $1", item_id
            )
        return result != "DELETE 0"
