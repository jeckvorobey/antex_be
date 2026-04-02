"""Создание дефолтного администратора."""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.admin import AdminRepository

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin"


async def seed_admin(db: AsyncSession) -> None:
    repo = AdminRepository(db)
    existing = await repo.get_by_username(DEFAULT_USERNAME)
    if existing:
        return

    password_hash = hashlib.sha256(DEFAULT_PASSWORD.encode()).hexdigest()
    await repo.create(username=DEFAULT_USERNAME, password_hash=password_hash)
    logger.info("Created default admin")
