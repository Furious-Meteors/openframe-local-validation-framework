import json
from typing import Any, Dict, List

from aiokafka import AIOKafkaProducer

from domain.event import OrderEvent


class KafkaEventPublisher:
    def __init__(self, producer: AIOKafkaProducer, topic: str) -> None:
        self._producer = producer
        self._topic = topic

    async def publish(self, event: OrderEvent) -> None:
        value = json.dumps(event.model_dump()).encode()
        await self._producer.send_and_wait(self._topic, value=value)

    async def publish_batch(self, events: List[OrderEvent]) -> None:
        for event in events:
            value = json.dumps(event.model_dump()).encode()
            await self._producer.send(self._topic, value=value)
        await self._producer.flush()

    async def topic_metadata(self) -> Dict[str, Any]:
        partitions = await self._producer.partitions_for(self._topic)
        return {
            "topic": self._topic,
            "partitions": sorted(partitions),
            "partition_count": len(partitions),
        }
