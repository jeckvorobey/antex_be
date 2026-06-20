"""Провайдеры аудитории рассылок."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass(slots=True)
class BroadcastRecipient:
    user_id: int
    chat_id: int


class TelegramUserAudienceProvider:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _recipients_statement():
        return (
            select(User)
            .where(User.is_bot.is_(False))
            .where(User.telegram_id.is_not(None))
            .order_by(User.id.asc())
        )

    async def count_recipients(self) -> int:
        result = await self.session.execute(
            select(func.count(User.id))
            .where(User.is_bot.is_(False))
            .where(User.telegram_id.is_not(None))
        )
        return int(result.scalar_one())

    async def iter_recipients(self, *, batch_size: int = 500) -> AsyncIterator[BroadcastRecipient]:
        last_id = 0
        normalized_batch_size = max(batch_size, 1)

        while True:
            result = await self.session.execute(
                self._recipients_statement()
                .where(User.id > last_id)
                .limit(normalized_batch_size)
            )
            users = list(result.scalars().all())
            if not users:
                return

            for user in users:
                last_id = user.id
                if user.telegram_id is not None:
                    yield BroadcastRecipient(user_id=user.id, chat_id=user.telegram_id)

    async def list_recipients(self) -> list[BroadcastRecipient]:
        return [recipient async for recipient in self.iter_recipients()]
