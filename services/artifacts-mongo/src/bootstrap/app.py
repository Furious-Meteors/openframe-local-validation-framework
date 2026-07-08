"""
ApplicationBootstrap composition root — Stage 1 wiring, single adapter.

This is the ONLY file that imports from openframe.adapters and
openframe.core.runtime. bootstrap/dependencies.py reads the registered
port through _app.get(Capability.PERSISTENCE) instead of owning the
plugin directly.
"""
from __future__ import annotations

from openframe.adapters.db.mongo import MongoPlugin, MongoSettings
from openframe.core.runtime      import ApplicationBootstrap

from src.adapters.outbound.artifact_repository import ArtifactMongoRepository


class ArtifactsMongoApp(ApplicationBootstrap):
    """ApplicationBootstrap subclass wiring a single MongoPlugin."""

    def configure(self) -> None:
        """Register the Mongo persistence plugin."""
        # repository_class ensures get_repository() returns ArtifactMongoRepository,
        # not the plain base MongoRepository. Without this, _doc_to_entity()/
        # _entity_to_doc() overrides are silently discarded.
        self.register(MongoPlugin(
            MongoSettings(),
            collection="artifacts",
            repository_class=ArtifactMongoRepository,
        ))
