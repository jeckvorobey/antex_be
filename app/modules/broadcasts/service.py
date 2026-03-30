"""Сервис создания и чтения рассылок."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.broadcasts.models import Broadcast
from app.modules.broadcasts.repository import BroadcastRepository
from app.modules.broadcasts.schemas import BroadcastCreate


@dataclass(frozen=True, slots=True)
class BroadcastSpeedConfig:
    target_rps: int
    worker_count: int
    effective_mode: str


def get_speed_config(speed_mode: str) -> BroadcastSpeedConfig:
    if speed_mode == "paid":
        return BroadcastSpeedConfig(target_rps=1000, worker_count=64, effective_mode="paid")
    return BroadcastSpeedConfig(target_rps=28, worker_count=8, effective_mode="free")


async def create_broadcast(
    db: AsyncSession,
    *,
    payload: BroadcastCreate,
    admin_id: int,
) -> Broadcast:
    repo = BroadcastRepository(db)
    if await repo.has_active_broadcast():
        raise HTTPException(status_code=409, detail="Another broadcast is already running")

    speed = get_speed_config(payload.speed_mode)
    try:
        broadcast = await repo.create(
            status="pending",
            audience_type="all_non_bot_users",
            text=payload.text,
            format=payload.format,
            button_text=payload.button_text,
            button_url=payload.button_url,
            speed_mode_requested=payload.speed_mode,
            speed_mode_effective=speed.effective_mode,
            target_rps=speed.target_rps,
            worker_count=speed.worker_count,
            total_count=0,
            success_count=0,
            failed_count=0,
            created_by_admin_id=admin_id,
            started_at=None,
            finished_at=None,
            last_error=None,
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another broadcast is already running",
        ) from exc

    await db.refresh(broadcast)
    return broadcast


async def list_broadcasts(
    db: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
) -> list[Broadcast]:
    repo = BroadcastRepository(db)
    return await repo.get_recent(limit=limit, offset=offset)
