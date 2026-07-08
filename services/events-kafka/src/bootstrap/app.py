"""
ApplicationBootstrap composition root — Stage 1 wiring, single adapter.

This is the ONLY file that imports from openframe.adapters and
openframe.core.runtime. bootstrap/dependencies.py reads the registered
port through _app.get(Capability.QUEUE) instead of owning the plugin
directly.

KafkaPlugin.initialize() starts the producer internally (calls
producer.start()), replacing what dependencies.py used to do manually
before this migration.

Note: KafkaPlugin.make_consumer() (unlike get_producer(), which honours
producer_class=) always constructs the plain base KafkaConsumer — its own
docstring flags this as a known gap ("Consumer subclass support is a
follow-up"). Using it here would silently drop OrderEventConsumer's
_deserialise() override and hand the background consumer task raw dicts
instead of typed OrderEvent objects. dependencies.make_consumer() therefore
constructs OrderEventConsumer directly against self.settings, bypassing
the plugin's make_consumer() — see settings below.
"""
from __future__ import annotations

from openframe.adapters.queue.kafka import KafkaPlugin, KafkaSettings
from openframe.core.runtime         import ApplicationBootstrap

from src.adapters.outbound.order_producer import OrderEventProducer


class EventsKafkaApp(ApplicationBootstrap):
    """ApplicationBootstrap subclass wiring a single KafkaPlugin."""

    def __init__(self) -> None:
        super().__init__()
        # Set by configure() (called from start()), not here — constructing
        # KafkaSettings() eagerly in __init__ would run env validation at
        # EventsKafkaApp() construction time (module import), before test
        # fixtures have a chance to set KAFKA_BOOTSTRAP_SERVERS via monkeypatch.
        self.settings: KafkaSettings | None = None

    def configure(self) -> None:
        """Register the Kafka queue plugin."""
        self.settings = KafkaSettings()
        # producer_class ensures get_producer() returns OrderEventProducer,
        # not the plain base KafkaProducer. Without this, _serialise() and
        # publish_keyed()/get_topic_metadata() overrides are silently
        # discarded.
        self.register(KafkaPlugin(
            self.settings,
            producer_class=OrderEventProducer,
        ))
