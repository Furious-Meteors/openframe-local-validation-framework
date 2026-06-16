from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from openframe.core.testing.fixtures import *  # noqa: F401, F403

from src.domain.artifact import EmbeddingStatus, ResearchArtifact


@pytest.fixture
def artifact_factory():
    def _make(
        id: str = "art-1",
        title: str = "Test Paper",
        source: str = "arxiv",
        tags: list[str] | None = None,
        embedding_status: EmbeddingStatus = EmbeddingStatus.PENDING,
    ) -> ResearchArtifact:
        return ResearchArtifact(
            id=id,
            title=title,
            source=source,
            tags=tags or ["ml"],
            embedding_status=embedding_status,
        )
    return _make


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get            = AsyncMock(return_value=None)
    repo.list           = AsyncMock(return_value=([], 0))
    repo.create         = AsyncMock()
    repo.update         = AsyncMock(return_value=None)
    repo.delete         = AsyncMock(return_value=False)
    repo.search         = AsyncMock(return_value=[])
    repo.filter_by_tags = AsyncMock(return_value=[])
    repo.ping           = AsyncMock(return_value=True)
    repo.is_ready       = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def service(mock_repo):
    from src.application.services.artifact_service import ArtifactService
    return ArtifactService(mock_repo)


@pytest.fixture
def mock_collection():
    col = MagicMock()
    col.find_one            = AsyncMock(return_value=None)
    col.insert_one          = AsyncMock()
    col.find_one_and_update = AsyncMock(return_value=None)
    col.delete_one          = AsyncMock()
    col.count_documents     = AsyncMock(return_value=0)
    cursor = MagicMock()
    cursor.sort    = MagicMock(return_value=cursor)
    cursor.limit   = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    col.find = MagicMock(return_value=cursor)
    return col, cursor


@pytest.fixture
def mock_settings():
    from openframe.adapters.db.mongo import MongoSettings
    return MongoSettings(
        mongo_url="mongodb://test:test@localhost:27017",
        mongo_database="test_db",
    )


@pytest.fixture
def adapter(mock_settings, mock_collection):
    col, cursor = mock_collection
    import openframe.adapters.db.mongo.connection as conn_module
    mock_client = MagicMock()
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    db.list_collection_names = AsyncMock(return_value=["artifacts"])
    mock_client.__getitem__ = MagicMock(return_value=db)
    mock_client.admin = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    conn_module._client_cache[mock_settings.mongo_url] = mock_client
    from src.adapters.outbound.artifact_repository import ArtifactMongoRepository
    repo = ArtifactMongoRepository(mock_settings)
    yield repo, col, cursor
    conn_module._client_cache.clear()
