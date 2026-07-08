"""
ApplicationBootstrap composition root — Stage 1 wiring with adapter swap.

One plugin is registered at startup — chosen by PERSISTENCE_BACKEND:
    postgres (default) → PostgresPlugin  → PostgresSwapRepository
    mongo              → MongoPlugin     → MongoSwapRepository

The service (SwapItemService) and all routes are identical for both backends.
Only this file and the two adapter files know which backend is active.

This is the canonical proof that the hexagonal contract holds:
the same SwapItemRepository port, satisfied by two different adapter
implementations, selected entirely at startup without touching any
service or route code.

This is the ONLY file that imports from openframe.adapters and
openframe.core.runtime.
"""
from __future__ import annotations

import os

from openframe.adapters.db.mongo    import MongoPlugin, MongoSettings
from openframe.adapters.db.postgres import PostgresPlugin, PostgresSettings
from openframe.core.runtime         import ApplicationBootstrap

from adapters.outbound.mongo_swap_repository    import MongoSwapRepository
from adapters.outbound.postgres_swap_repository import PostgresSwapRepository


class SwapDemoApp(ApplicationBootstrap):
    """
    ApplicationBootstrap subclass wiring exactly one persistence plugin,
    selected by PERSISTENCE_BACKEND — never both.

    Registering both plugins unconditionally (e.g. via get_all()) would
    open a live connection to the backend NOT in use, which is a real
    resource-cost regression and breaks the "only one backend's connection
    is ever opened" invariant this service exists to demonstrate.
    """

    def __init__(self) -> None:
        super().__init__()
        # Read once at construction — not at module-import time (would
        # freeze the value across every SwapDemoApp() built in this
        # process, breaking monkeypatch.setenv() in tests) and not inside
        # configure() (construction is the more natural point to snapshot
        # it, and it makes self._backend inspectable before start()).
        self._backend = os.getenv("PERSISTENCE_BACKEND", "postgres")

    def configure(self) -> None:
        """Register exactly one plugin, gated by self._backend."""
        if self._backend == "mongo":
            self.register(MongoPlugin(
                MongoSettings(),
                collection="swap_items",
                repository_class=MongoSwapRepository,
            ))
        else:
            self.register(PostgresPlugin(
                PostgresSettings(),
                table="swap_items",
                id_column="id",
                repository_class=PostgresSwapRepository,
            ))
