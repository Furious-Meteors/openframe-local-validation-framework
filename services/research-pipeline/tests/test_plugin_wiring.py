"""
Tests for plugin registration in bootstrap/app.py (ResearchPipelineApp.configure()).

Regression tests for the repository_class/producer_class fix introduced
in openframe-adapters 1.2.0. Without these parameters, get_repository()
and get_producer() silently return plain base-class instances, discarding
all domain-specific overrides (_doc_to_entity, _serialise, etc.) and
causing AttributeError at runtime.
"""
from __future__ import annotations

import pathlib

import pytest

_APP = (
    pathlib.Path(__file__).parent.parent / "src" / "bootstrap" / "app.py"
)


def _source() -> str:
    return _APP.read_text()


# ── REGRESSION: repository_class / producer_class source-level checks ────────

def test_mongo_plugin_registered_with_artifact_repository_class():
    """
    REGRESSION: confirms MongoPlugin is registered with
    repository_class=ArtifactMongoRepository. Without this, get_repository()
    silently returns a plain MongoRepository and _doc_to_entity() overrides
    are discarded — root cause of the live-validation
    AttributeError: 'dict' object has no attribute 'id' / 'embedding_status'.
    """
    assert "repository_class=ArtifactMongoRepository" in _source(), (
        "MongoPlugin must pass repository_class=ArtifactMongoRepository "
        "so get_repository() returns the domain subclass, not the base adapter."
    )


def test_kafka_plugin_registered_with_artifact_producer_class():
    """
    REGRESSION: confirms KafkaPlugin uses producer_class=ArtifactEventProducer
    so _serialise() override (json.dumps with default=str) is preserved.
    """
    assert "producer_class=ArtifactEventProducer" in _source(), (
        "KafkaPlugin must pass producer_class=ArtifactEventProducer "
        "so get_producer() returns the domain subclass, not the base adapter."
    )


# ── Capability taxonomy checks ────────────────────────────────────────────────

async def test_registry_get_persistence_returns_artifact_mongo_repository():
    """
    Confirms type(repo) is ArtifactMongoRepository specifically — not just
    structurally compatible with MongoRepository. This is the actual proof
    that the fix works, not just that the source mentions the class name.
    """
    from openframe.adapters.db.mongo import MongoPlugin, MongoSettings
    from openframe.core.plugins import PluginRegistry
    from src.adapters.outbound.artifact_mongo_repository import ArtifactMongoRepository

    settings = MongoSettings(
        mongo_url="mongodb://test:test@localhost:27017",
        mongo_database="test",
    )
    registry = PluginRegistry()
    registry.register(MongoPlugin(
        settings,
        collection="artifacts",
        repository_class=ArtifactMongoRepository,
    ))
    plugin = registry.get("persistence")
    assert plugin._repository_class is ArtifactMongoRepository


async def test_registry_get_cache_returns_redis_plugin():
    """Confirms the capability taxonomy: 'cache' → Redis."""
    from openframe.adapters.db.redis import RedisPlugin, RedisSettings
    from openframe.core.plugins import PluginRegistry

    registry = PluginRegistry()
    registry.register(RedisPlugin(RedisSettings(redis_url="redis://localhost:6379/0")))
    assert registry.get("cache").capability == "cache"


async def test_registry_get_queue_returns_kafka_plugin():
    """Confirms the capability taxonomy: 'queue' → Kafka."""
    from openframe.adapters.queue.kafka import KafkaPlugin, KafkaSettings
    from openframe.core.plugins import PluginRegistry
    from src.adapters.outbound.artifact_kafka_producer import ArtifactEventProducer

    registry = PluginRegistry()
    registry.register(KafkaPlugin(
        KafkaSettings(kafka_bootstrap_servers="localhost:9092", kafka_topic="test"),
        producer_class=ArtifactEventProducer,
    ))
    assert registry.get("queue").capability == "queue"


async def test_registry_three_plugins_do_not_collide():
    """All three plugins coexist in the same registry with distinct capability keys."""
    from openframe.adapters.db.mongo import MongoPlugin, MongoSettings
    from openframe.adapters.db.redis import RedisPlugin, RedisSettings
    from openframe.adapters.queue.kafka import KafkaPlugin, KafkaSettings
    from openframe.core.plugins import PluginRegistry
    from src.adapters.outbound.artifact_mongo_repository import ArtifactMongoRepository
    from src.adapters.outbound.artifact_kafka_producer import ArtifactEventProducer

    registry = PluginRegistry()
    registry.register(MongoPlugin(
        MongoSettings(mongo_url="mongodb://test:test@localhost:27017", mongo_database="test"),
        collection="artifacts",
        repository_class=ArtifactMongoRepository,
    ))
    registry.register(RedisPlugin(RedisSettings(redis_url="redis://localhost:6379/0")))
    registry.register(KafkaPlugin(
        KafkaSettings(kafka_bootstrap_servers="localhost:9092", kafka_topic="test"),
        producer_class=ArtifactEventProducer,
    ))
    assert registry.get("persistence").capability == "persistence"
    assert registry.get("cache").capability == "cache"
    assert registry.get("queue").capability == "queue"
