"""Административный API для рассылок."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AdminUser, DbDep
from app.modules.broadcasts.runner import schedule_broadcast, stop_broadcast
from app.modules.broadcasts.schemas import (
    BroadcastCreate,
    BroadcastOut,
    PaginatedBroadcastsResponse,
)
from app.modules.broadcasts.service import create_broadcast, list_broadcasts

router = APIRouter(prefix="/api/admin/broadcasts", tags=["admin-broadcasts"])


@router.get("", response_model=PaginatedBroadcastsResponse)
async def get_broadcasts(
    db: DbDep,
    _: AdminUser,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> PaginatedBroadcastsResponse:
    items = await list_broadcasts(db, limit=limit, offset=offset)
    from app.modules.broadcasts.repository import BroadcastRepository

    total = await BroadcastRepository(db).count_all()
    return PaginatedBroadcastsResponse(
        items=[BroadcastOut.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=BroadcastOut, status_code=status.HTTP_201_CREATED)
async def create_broadcast_route(
    payload: BroadcastCreate,
    db: DbDep,
    admin: AdminUser,
) -> BroadcastOut:
    broadcast = await create_broadcast(db, payload=payload, admin_id=admin.id)  # type: ignore[attr-defined]
    await schedule_broadcast(broadcast_id=broadcast.id)
    return BroadcastOut.model_validate(broadcast)


@router.post("/{broadcast_id}/stop", response_model=BroadcastOut)
async def stop_broadcast_route(
    broadcast_id: int,
    db: DbDep,
    _: AdminUser,
) -> BroadcastOut:
    broadcast = await stop_broadcast(broadcast_id=broadcast_id, session=db)
    if broadcast is None:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return BroadcastOut.model_validate(broadcast)
