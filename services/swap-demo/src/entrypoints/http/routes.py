import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from application.services.swap_item_service import SwapItemService
from bootstrap.dependencies import get_swap_item_service
from domain.swap_item import SwapItem

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    backend = os.getenv("PERSISTENCE_BACKEND", "postgres")
    return {"status": "ok", "service": "swap-demo", "backend": backend}


@router.get("/info")
async def info() -> dict:
    backend = os.getenv("PERSISTENCE_BACKEND", "postgres")
    return {
        "service": "swap-demo",
        "persistence_backend": backend,
        "description": "Adapter swap via PERSISTENCE_BACKEND env var (postgres | mongo)",
    }


@router.post("/items", status_code=status.HTTP_201_CREATED, response_model=SwapItem)
async def create_item(
    item: SwapItem,
    svc: SwapItemService = Depends(get_swap_item_service),
) -> SwapItem:
    return await svc.create(item)


@router.get("/items/{item_id}", response_model=SwapItem)
async def get_item(
    item_id: str,
    svc: SwapItemService = Depends(get_swap_item_service),
) -> SwapItem:
    found = await svc.get(item_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return found


@router.get("/items", response_model=List[SwapItem])
async def list_items(
    svc: SwapItemService = Depends(get_swap_item_service),
) -> List[SwapItem]:
    return await svc.list()


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    svc: SwapItemService = Depends(get_swap_item_service),
) -> None:
    deleted = await svc.delete(item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Item not found")
