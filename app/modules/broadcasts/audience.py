"""Провайдеры аудитории рассылок."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

MINIAPP_GUEST_USER_ID = 9_999_001


@dataclass(slots=True)
class BroadcastRecipient:
    user_id: int
    chat_id: int


class TelegramUserAudienceProvider:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_recipients(self) -> list[BroadcastRecipient]:
        result = await self.session.execute(
            select(User)
            .where(User.is_bot.is_(False))
            .where(User.telegram_id.is_not(None))
            .where(User.id != MINIAPP_GUEST_USER_ID)
            .order_by(User.id.asc())
        )
        users = result.scalars().all()
        return [
            BroadcastRecipient(user_id=user.id, chat_id=user.telegram_id)
            for user in users
            if user.telegram_id is not None
        ]
