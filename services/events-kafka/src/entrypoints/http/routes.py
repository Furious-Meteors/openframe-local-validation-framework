"""HTTP routes for the events service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from src.application.services.event_service import EventService
from src.bootstrap.dependencies import get_event_service
from src.domain.order_event import OrderEvent

router = APIRouter(prefix="/events")


@router.post("", status_code=201)
async def publish_event(
    event:   OrderEvent,
    service: EventService = Depends(get_event_service),
):
    """Publish a single order event to Kafka."""
    await service.publish_event(event)
    return {"published": 1, "order_id": event.order_id}


@router.post("/batch", status_code=201)
async def publish_batch(
    events:  list[OrderEvent],
    service: EventService = Depends(get_event_service),
):
    """Publish multiple events in one call."""
    await service.publish_batch(events)
    return {"published": len(events)}


@router.post("/keyed", status_code=201)
async def publish_keyed(
    event:   OrderEvent,
    service: EventService = Depends(get_event_service),
):
    """
    Publish with partition key = order_id.
    Niche aiokafka feature — same order always goes to same partition.
    """
    await service.publish_keyed(event.order_id, event)
    return {"published": 1, "key": event.order_id}


@router.get("/metadata")
async def topic_metadata(
    service: EventService = Depends(get_event_service),
):
    """Topic metadata from Kafka broker — niche aiokafka feature."""
    return await service.get_topic_metadata()


@router.get("/received")
async def get_received(
    service: EventService = Depends(get_event_service),
):
    """Return all events received by the background consumer."""
    received = service.get_received()
    return {"events": received, "count": len(received)}
