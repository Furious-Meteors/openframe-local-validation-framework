"""
Shared fixtures for research-pipeline tests.

OTel reset provided by openframe.core.testing.fixtures.
The autouse _test_env fixture sets required env vars so that
TestClient(app) — which triggers the real lifespan — does not
raise pydantic ValidationError when constructing MongoSettings,
RedisSettings, or KafkaSettings. Actual connection attempts will
still fail with AdapterConnectionError, which lifespan now catches
and logs as degraded mode (see main.py fix above).
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from openframe.core.ports import PluginHealth, PluginStatus
from openframe.core.testing.fixtures import *  # noqa: F401, F403

from src.domain.artifact import ArtifactEvent, EmbeddingStatus, ResearchArtifact


@pytest.fixture(autouse=True)
def _test_env(monkeypatch):
    """Ensure Settings() construction never raises ValidationError in tests."""
    monkeypatch.setenv("MONGO_URL", "mongodb://test:test@localhost:27017")
    monkeypatch.setenv("MONGO_DATABASE", "test")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")


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
            id=id, title=title, source=source,
            tags=tags or ["ml"], embedding_status=embedding_status,
        )
    return _make


@pytest.fixture
def mock_persistence():
    """Mocked ArtifactRepositoryPort — represents MongoDB."""
    repo = MagicMock()
    repo.get      = AsyncMock(return_value=None)
    repo.list     = AsyncMock(return_value=([], 0))
    repo.create   = AsyncMock()
    repo.update   = AsyncMock(return_value=None)
    repo.delete   = AsyncMock(return_value=False)
    repo.health   = AsyncMock(return_value=PluginHealth(status=PluginStatus.READY))
    return repo


@pytest.fixture
def mock_cache():
    """Mocked ArtifactRepositoryPort — represents Redis status cache."""
    repo = MagicMock()
    repo.get      = AsyncMock(return_value=None)
    repo.list     = AsyncMock(return_value=([], 0))
    repo.create   = AsyncMock()
    repo.update   = AsyncMock(return_value=None)
    repo.delete   = AsyncMock(return_value=False)
    repo.health   = AsyncMock(return_value=PluginHealth(status=PluginStatus.READY))
    return repo


@pytest.fixture
def mock_publisher():
    """Mocked EventPublisherPort — represents Kafka producer."""
    pub = MagicMock()
    pub.publish = AsyncMock()
    pub.close   = AsyncMock()
    return pub


@pytest.fixture
def service(mock_persistence, mock_cache, mock_publisher):
    from src.application.services.pipeline_service import ResearchPipelineService
    return ResearchPipelineService(
        persistence=mock_persistence,
        cache=mock_cache,
        publisher=mock_publisher,
    )


# ── Mongo adapter fixtures ──────────────────────────────────────────────────

@pytest.fixture
def mock_mongo_collection():
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
def mongo_settings():
    from openframe.adapters.db.mongo import MongoSettings
    return MongoSettings(
        mongo_url="mongodb://test:test@localhost:27017",
        mongo_database="test_db",
    )


@pytest.fixture
def mongo_adapter(mongo_settings, mock_mongo_collection):
    col, cursor = mock_mongo_collection
    import openframe.adapters.db.mongo.connection as conn_module
    mock_client = MagicMock()
    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=col)
    db.list_collection_names = AsyncMock(return_value=["artifacts"])
    mock_client.__getitem__ = MagicMock(return_value=db)
    mock_client.admin = MagicMock()
    mock_client.admin.command = AsyncMock(return_value={"ok": 1})
    conn_module._client_cache[mongo_settings.mongo_url] = mock_client
    from src.adapters.outbound.artifact_mongo_repository import ArtifactMongoRepository
    r = ArtifactMongoRepository(mongo_settings)
    yield r, col, cursor
    conn_module._client_cache.clear()


# ── Redis adapter fixtures ───────────────────────────────────────────────────

@pytest.fixture
def mock_redis_client():
    client = MagicMock()
    client.get    = AsyncMock(return_value=None)
    client.set    = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    client.ping   = AsyncMock(return_value=True)
    client.info   = AsyncMock(return_value={"redis_version": "7.0.0"})

    async def _scan_iter(match=None, count=None):
        return
        yield
    client.scan_iter = _scan_iter
    return client


@pytest.fixture
def redis_settings():
    from openframe.adapters.db.redis import RedisSettings
    return RedisSettings(redis_url="redis://localhost:6379/0")


@pytest.fixture
def redis_adapter(redis_settings, mock_redis_client):
    import openframe.adapters.db.redis.connection as conn_module
    conn_module._client_cache[redis_settings.redis_url] = mock_redis_client
    from src.adapters.outbound.artifact_redis_cache import ArtifactRedisCache
    r = ArtifactRedisCache(redis_settings)
    yield r, mock_redis_client
    conn_module._client_cache.clear()


# ── Kafka adapter fixtures ───────────────────────────────────────────────────

@pytest.fixture
def mock_kafka_producer_client():
    p = MagicMock()
    p.start         = AsyncMock()
    p.stop          = AsyncMock()
    p.send_and_wait = AsyncMock()
    return p


@pytest.fixture
def kafka_settings():
    from openframe.adapters.queue.kafka import KafkaSettings
    return KafkaSettings(
        kafka_bootstrap_servers="localhost:9092",
        kafka_topic="artifact-events",
    )


@pytest.fixture
def kafka_adapter(kafka_settings, mock_kafka_producer_client):
    from src.adapters.outbound.artifact_kafka_producer import ArtifactEventProducer
    p = ArtifactEventProducer(kafka_settings)
    p._producer = mock_kafka_producer_client
    yield p, mock_kafka_producer_client
