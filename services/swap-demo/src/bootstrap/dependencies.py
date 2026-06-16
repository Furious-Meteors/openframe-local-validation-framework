import os
from typing import Optional

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from adapters.outbound.mongo_swap_repository import MongoSwapRepository
from adapters.outbound.postgres_swap_repository import PostgresSwapRepository
from application.services.swap_item_service import SwapItemService

_BACKEND = os.getenv("PERSISTENCE_BACKEND", "postgres")

_pool: Optional[asyncpg.Pool] = None
_mongo_client: Optional[AsyncIOMotorClient] = None
_mongo_collection: Optional[AsyncIOMotorCollection] = None


async def init_backends() -> None:
    global _pool, _mongo_client, _mongo_collection
    if _BACKEND == "mongo":
        _mongo_client = AsyncIOMotorClient(
            os.getenv("MONGO_URL", "mongodb://openframe:openframe@localhost:27017")
        )
        db = _mongo_client[os.getenv("MONGO_DATABASE", "openframe")]
        _mongo_collection = db["swap_items"]
    else:
        _pool = await asyncpg.create_pool(
            dsn=os.getenv(
                "DATABASE_URL",
                "postgresql://openframe:openframe@localhost:5432/openframe",
            ),
            min_size=1,
            max_size=int(os.getenv("POOL_SIZE", "5")),
        )


async def close_backends() -> None:
    global _pool, _mongo_client
    if _pool is not None:
        await _pool.close()
        _pool = None
    if _mongo_client is not None:
        _mongo_client.close()
        _mongo_client = None


def get_swap_item_service() -> SwapItemService:
    if _BACKEND == "mongo":
        assert _mongo_collection is not None, "MongoDB not initialized"
        return SwapItemService(MongoSwapRepository(_mongo_collection))
    assert _pool is not None, "Postgres pool not initialized"
    return SwapItemService(PostgresSwapRepository(_pool))
