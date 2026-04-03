"""Сервис аутентификации (Telegram initData → JWT)."""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, validate_telegram_init_data
from app.exceptions import AntExException
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse


async def telegram_auth(db: AsyncSession, init_data: str) -> TokenResponse:
    parsed = validate_telegram_init_data(init_data)
    if not parsed:
        raise AntExException("Invalid Telegram initData", code="INVALID_INIT_DATA", status_code=401)

    user_raw = parsed.get("user")
    if not user_raw:
        raise AntExException("No user in initData", code="NO_USER_DATA", status_code=401)

    try:
        user_data: dict = json.loads(user_raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise AntExException("Malformed user data", code="BAD_USER_DATA", status_code=401) from exc

    tg_id: int = int(user_data["id"])
    repo = UserRepository(db)
    user, _ = await repo.find_or_create(
        tg_id,
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        language_code=user_data.get("language_code"),
        is_bot=user_data.get("is_bot", False),
        is_premium=user_data.get("is_premium", False),
    )

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token)
