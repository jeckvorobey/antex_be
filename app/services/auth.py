"""Сервис аутентификации (Telegram initData → JWT)."""

from __future__ import annotations

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, validate_telegram_init_data
from app.exceptions import AntExException
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse, TrustedContactResponse, build_trusted_contact

logger = logging.getLogger(__name__)
MARKETING_START_PARAM_PREFIX = "market_"


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
        photo_url=user_data.get("photo_url"),
        is_bot=user_data.get("is_bot", False),
        is_premium=user_data.get("is_premium", False),
    )

    start_param = parsed.get("start_param")
    if isinstance(start_param, str) and start_param.startswith(MARKETING_START_PARAM_PREFIX):
        from app.modules.marketing.service import MarketingService

        code = start_param.removeprefix(MARKETING_START_PARAM_PREFIX)
        try:
            await MarketingService(db).attribute_user(user.id, code)
        except AntExException as exc:
            logger.info(
                "Marketing attribution skipped: code=%s user_id=%s",
                exc.code,
                user.id,
            )
        except Exception:
            logger.exception("Marketing attribution failed for user_id=%s", user.id)

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token)


def resolve_trusted_contact(user) -> TrustedContactResponse:
    return build_trusted_contact(user)


async def save_trusted_phone(
    db: AsyncSession,
    user_id: int,
    phone: str,
) -> TrustedContactResponse:
    user = await UserRepository(db).set_phone(user_id, phone)
    if user is None:
        raise AntExException("User not found", code="USER_NOT_FOUND", status_code=404)
    return resolve_trusted_contact(user)
