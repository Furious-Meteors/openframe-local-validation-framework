"""
ApplicationBootstrap composition root — Stage 1 wiring, single adapter.

This is the ONLY file that imports from openframe.adapters and
openframe.core.runtime.

Note: RedisPlugin (unlike PostgresPlugin/MongoPlugin/KafkaPlugin) has no
repository_class= parameter — get_repository() always returns the base
RedisRepository, never a domain subclass. RedisPlugin is still registered
here so ApplicationBootstrap manages its lifecycle (initialize/shutdown/
health), but the actual SessionRedisRepository instance handed to the
service is constructed directly in dependencies.py from this app's
settings, bypassing get_repository() — see get_session_service() for why.
"""
from __future__ import annotations

from openframe.adapters.db.redis import RedisPlugin, RedisSettings
from openframe.core.runtime      import ApplicationBootstrap


class CacheRedisApp(ApplicationBootstrap):
    """ApplicationBootstrap subclass wiring a single RedisPlugin."""

    def __init__(self) -> None:
        super().__init__()
        # Set by configure() (called from start()), not here — constructing
        # RedisSettings() eagerly in __init__ would run env validation at
        # CacheRedisApp() construction time (module import), before test
        # fixtures have a chance to set REDIS_URL via monkeypatch.
        self.settings: RedisSettings | None = None

    def configure(self) -> None:
        """Register the Redis cache plugin."""
        self.settings = RedisSettings()
        self.register(RedisPlugin(self.settings))
