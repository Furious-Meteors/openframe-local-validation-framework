from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from domain.artifact import Artifact


def _to_artifact(doc: Dict[str, Any]) -> Artifact:
    doc = dict(doc)
    doc["id"] = doc.pop("_id")
    return Artifact(**doc)


class MongoArtifactRepository:
    def __init__(self, collection: AsyncIOMotorCollection) -> None:
        self._col = collection

    async def save(self, artifact: Artifact) -> None:
        doc = artifact.model_dump()
        doc["_id"] = doc.pop("id")
        doc.setdefault("created_at", datetime.now(timezone.utc))
        await self._col.replace_one({"_id": doc["_id"]}, doc, upsert=True)

    async def get(self, artifact_id: str) -> Optional[Artifact]:
        doc = await self._col.find_one({"_id": artifact_id})
        if doc is None:
            return None
        return _to_artifact(doc)

    async def list(self, tags: Optional[List[str]] = None) -> List[Artifact]:
        query: Dict[str, Any] = {}
        if tags:
            query["tags"] = {"$in": tags}
        docs = await self._col.find(query).to_list(length=None)
        return [_to_artifact(d) for d in docs]

    async def search(self, q: str) -> List[Artifact]:
        docs = await self._col.find(
            {"title": {"$regex": q, "$options": "i"}}
        ).to_list(length=None)
        return [_to_artifact(d) for d in docs]

    async def delete(self, artifact_id: str) -> bool:
        result = await self._col.delete_one({"_id": artifact_id})
        return result.deleted_count > 0
