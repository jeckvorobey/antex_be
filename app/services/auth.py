"""Сервис аутентификации (Telegram initData → JWT)."""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, validate_telegram_init_data
from app.exceptions import AntExException
from app.repositories.user import UserRepository
from app.schemas.auth import TokenResponse, TrustedContactResponse, build_trusted_contact
from app.services.referral import ReferralService

REFERRAL_START_PARAM_PREFIX = "ref_"
logger = logging.getLogger(__name__)
MARKETING_START_PARAM_PREFIX = "market_"


async def telegram_auth(db: AsyncSession, init_data: str) -> TokenResponse:
    """Авторизовать Mini App пользователя и применить referral/marketing start_param."""
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
    user, is_new_user = await repo.find_or_create(
        tg_id,
        username=user_data.get("username"),
        first_name=user_data.get("first_name"),
        last_name=user_data.get("last_name"),
        language_code=user_data.get("language_code"),
        photo_url=user_data.get("photo_url"),
        is_bot=user_data.get("is_bot", False),
        is_premium=user_data.get("is_premium", False),
    )
    referral_code = extract_referral_code_from_start_param(parsed.get("start_param"))
    if referral_code and is_new_user:
        try:
            await ReferralService().bind_referral(db, user, referral_code)
        except AntExException as exc:
            logger.info(
                "Referral start_param ignored during auth: user_id=%s, code=%s, error_code=%s",
                user.id,
                referral_code,
                exc.code,
            )
    elif referral_code:
        from app.services.attribution import AttributionService

        await AttributionService(db).audit(
            user.id,
            "referral_binding_rejected",
            reason="existing_user",
        )

    start_param = parsed.get("start_param")
    marketing_touch_created = False
    if isinstance(start_param, str) and start_param.startswith(MARKETING_START_PARAM_PREFIX):
        code = start_param.removeprefix(MARKETING_START_PARAM_PREFIX)
        try:
            from app.services.attribution import AttributionService

            touch = await AttributionService(db).record_marketing_touch(
                user.id,
                code,
                is_new_user=is_new_user,
                session_key=_marketing_session_key(parsed, tg_id, start_param),
            )
            marketing_touch_created = True
            if is_new_user:
                await AttributionService(db).ensure_acquisition(
                    user.id, source_type="campaign", campaign_id=touch.campaign_id
                )
        except (AntExException, ValueError) as exc:
            logger.info(
                "Marketing attribution skipped: code=%s user_id=%s",
                getattr(exc, "code", str(exc)),
                user.id,
            )
        except Exception:
            logger.exception("Marketing attribution failed for user_id=%s", user.id)

    if is_new_user:
        from app.services.attribution import AttributionService

        if referral_code and user.referred_by is not None:
            await AttributionService(db).ensure_acquisition(
                user.id, source_type="referral", referrer_user_id=user.referred_by
            )
        elif not marketing_touch_created:
            await AttributionService(db).ensure_acquisition(user.id, source_type="direct")

    token = create_access_token({"sub": str(user.id), "role": user.role})
    return TokenResponse(access_token=token)


def extract_referral_code_from_start_param(start_param: object) -> str | None:
    """Извлечь referral-код из Telegram start_param формата ref_<code>."""
    if not isinstance(start_param, str):
        return None

    if not start_param.startswith(REFERRAL_START_PARAM_PREFIX):
        return None

    referral_code = start_param.removeprefix(REFERRAL_START_PARAM_PREFIX).strip()
    return referral_code or None


def _marketing_session_key(parsed: dict, telegram_id: int, start_param: str) -> str | None:
    """Дедуплицирует replay одного trusted Telegram initData без хранения initData."""
    query_id = parsed.get("query_id")
    auth_date = parsed.get("auth_date")
    if not isinstance(query_id, str) and not isinstance(auth_date, str | int):
        return None
    material = f"{telegram_id}:{query_id or ''}:{auth_date or ''}:{start_param}"
    return hashlib.sha256(material.encode()).hexdigest()


def resolve_trusted_contact(user) -> TrustedContactResponse:
    """Вернуть доверенный контакт пользователя для Mini App."""
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
