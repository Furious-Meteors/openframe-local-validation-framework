"""HTTP routes for the sessions service."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.application.services.session_service import SessionService
from src.bootstrap.dependencies import get_session_service
from src.domain.session import Session

router = APIRouter(prefix="/sessions")


class ExtendRequest(BaseModel):
    seconds: int = 3600


@router.get("", response_model=dict)
async def list_sessions(
    limit:   int = Query(20, ge=1, le=100),
    offset:  int = Query(0, ge=0),
    service: SessionService = Depends(get_session_service),
):
    sessions, total = await service.list_sessions(limit=limit, offset=offset)
    return {"sessions": sessions, "total": total}


@router.post("", response_model=Session, status_code=201)
async def create_session(
    session: Session,
    service: SessionService = Depends(get_session_service),
):
    return await service.create_session(session)


# /stats must be registered before /{session_id} to avoid path shadowing
@router.get("/stats")
async def get_stats(
    service: SessionService = Depends(get_session_service),
):
    """Redis server stats via PIPELINE — niche redis.asyncio feature."""
    return await service.get_stats()


@router.get("/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    service:    SessionService = Depends(get_session_service),
):
    session = await service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return session


@router.put("/{session_id}/extend")
async def extend_ttl(
    session_id: str,
    body:       ExtendRequest,
    service:    SessionService = Depends(get_session_service),
):
    """Extend session TTL using Redis EXPIRE — niche redis.asyncio feature."""
    ok = await service.extend_session(session_id, body.seconds)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
    return {"session_id": session_id, "extended_by_seconds": body.seconds}


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    service:    SessionService = Depends(get_session_service),
):
    deleted = await service.invalidate(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")
