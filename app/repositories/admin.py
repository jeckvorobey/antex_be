"""Репозиторий администраторов."""

from __future__ import annotations

from sqlalchemy import select

from app.models.admin import Admin
from app.repositories.base import BaseRepository


class AdminRepository(BaseRepository[Admin]):
    model = Admin

    async def get_by_username(self, username: str) -> Admin | None:
        result = await self.session.execute(select(Admin).where(Admin.username == username))
        return result.scalar_one_or_none()
