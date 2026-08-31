"""Создание дефолтного администратора."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.admin import build_password_hash
from app.core.config import settings
from app.repositories.admin import AdminRepository

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "admin"


async def seed_admin(db: AsyncSession) -> None:
    """Создаёт начального администратора только при заданном secret-пароле."""
    repo = AdminRepository(db)
    existing = await repo.get_by_username(DEFAULT_USERNAME)
    if existing:
        return

    password = settings.admin_bootstrap_password
    if not password:
        raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD is required for admin seed")

    password_hash = build_password_hash(password)
    await repo.create(
        username=DEFAULT_USERNAME,
        email="admin@example.com",
        password_hash=password_hash,
    )
    logger.info("Created bootstrap admin")
