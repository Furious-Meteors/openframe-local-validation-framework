"""
HTTP routes — identical shape to items-postgres.

The routes never know whether caching is involved.
The service handles the cache-aside logic transparently.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.application.services.item_service import ItemCachedService
from src.bootstrap.dependencies import get_item_service
from src.domain.item import Item

router = APIRouter(prefix="/items")


@router.get("", response_model=dict)
async def list_items(
    limit:   int = Query(20, ge=1, le=100),
    offset:  int = Query(0, ge=0),
    service: ItemCachedService = Depends(get_item_service),
):
    items, total = await service.list_items(limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=Item, status_code=201)
async def create_item(
    item:    Item,
    service: ItemCachedService = Depends(get_item_service),
):
    return await service.create_item(item)


@router.get("/{item_id}", response_model=Item)
async def get_item(
    item_id: str,
    service: ItemCachedService = Depends(get_item_service),
):
    """
    Cache-aside GET.

    Response is identical regardless of whether it came from
    Redis (cache hit) or Postgres (cache miss).
    Caller never knows which backend served the response.
    """
    item = await service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id!r} not found")
    return item


@router.put("/{item_id}", response_model=Item)
async def update_item(
    item_id: str,
    item:    Item,
    service: ItemCachedService = Depends(get_item_service),
):
    item = item.model_copy(update={"id": item_id})
    updated = await service.update_item(item)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id!r} not found")
    return updated


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: str,
    service: ItemCachedService = Depends(get_item_service),
):
    """Deletes from Postgres AND invalidates Redis cache."""
    deleted = await service.delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Item {item_id!r} not found")
