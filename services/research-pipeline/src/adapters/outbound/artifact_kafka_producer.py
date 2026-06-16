"""Kafka adapter for artifact event publishing."""
from __future__ import annotations

import json
from typing import Any

from openframe.adapters.queue.kafka import KafkaProducer


class ArtifactEventProducer(KafkaProducer[dict[str, Any]]):
    """
    Artifact event producer backed by Kafka.

    Publishes artifact lifecycle events to the configured topic.
    """

    def _serialise(self, message: dict[str, Any]) -> bytes:
        return json.dumps(message, default=str).encode("utf-8")
