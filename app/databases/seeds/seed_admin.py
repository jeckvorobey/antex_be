"""Создание дефолтного администратора."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.admin import build_password_hash
from app.repositories.admin import AdminRepository

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


async def seed_admin(db: AsyncSession) -> None:
    repo = AdminRepository(db)
    existing = await repo.get_by_username(DEFAULT_USERNAME)
    if existing:
        return

    password_hash = build_password_hash(DEFAULT_PASSWORD)
    await repo.create(
        username=DEFAULT_USERNAME,
        email="admin@example.com",
        password_hash=password_hash,
    )
    logger.info("Created default admin")
