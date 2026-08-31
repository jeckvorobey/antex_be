"""Зависимости FastAPI (get_db, get_current_user, get_admin)."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import decode_access_token
from app.enums.user import has_operator_access
from app.models.admin import Admin
from app.models.user import User
from app.repositories.admin import AdminRepository
from app.repositories.user import UserRepository

DbDep = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    token_type = payload.get("type")
    if token_type not in (None, "user"):
        raise HTTPException(status_code=403, detail="User access required")

    user_id = int(payload.get("sub", 0))
    repo = UserRepository(db)
    user = await repo.get_one(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_miniapp_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if authorization and authorization.startswith("Bearer "):
        return await get_current_user(db, authorization)

    if settings.app_env != "dev" or settings.dev_user_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = await UserRepository(db).get_by_telegram_id(settings.dev_user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Dev user not found")

    return user


async def get_admin(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Admin:
    """Авторизует административные операции только access-токеном."""
    return await _get_admin_by_token_type(db, authorization, expected_type="admin")


async def get_refresh_admin(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Admin:
    """Авторизует обновление сессии только административным refresh-токеном."""
    return await _get_admin_by_token_type(db, authorization, expected_type="admin_refresh")


async def _get_admin_by_token_type(
    db: DbDep,
    authorization: str | None,
    *,
    expected_type: str,
) -> Admin:
    """Проверяет JWT и возвращает администратора для строго заданного типа токена."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("type") != expected_type:
        raise HTTPException(status_code=403, detail="Admin access required")

    admin_id = int(payload.get("sub", 0))
    repo = AdminRepository(db)
    admin = await repo.get_by_id(admin_id)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    if int(payload.get("sv", 0)) != admin.session_version:
        raise HTTPException(status_code=401, detail="Admin session revoked")
    return admin


CurrentUser = Annotated[User, Depends(get_current_user)]
MiniappUser = Annotated[User, Depends(get_miniapp_user)]
AdminUser = Annotated[Admin, Depends(get_admin)]
RefreshAdminUser = Annotated[Admin, Depends(get_refresh_admin)]


async def get_manager_user(user: CurrentUser) -> User:
    """Разрешает операционный manager API только Telegram-пользователю менеджера."""
    if not has_operator_access(user.role):
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


ManagerUser = Annotated[User, Depends(get_manager_user)]
