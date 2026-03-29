"""Зависимости FastAPI (get_db, get_current_user, get_admin)."""

from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.admin import AdminRepository
from app.repositories.user import UserRepository

DbDep = Annotated[AsyncSession, Depends(get_db_session)]
MINIAPP_GUEST_USER_ID = 9_999_001


async def get_current_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = int(payload.get("sub", 0))
    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_miniapp_user(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if authorization and authorization.startswith("Bearer "):
        return await get_current_user(db, authorization)

    repo = UserRepository(db)
    user, _ = await repo.find_or_create(
        MINIAPP_GUEST_USER_ID,
        username="sergeywebdev",
        first_name="Sergei",
        last_name="V",
        language_code="ru",
        is_bot=False,
        is_premium=True,
        role=1,
    )
    user.username = "sergeywebdev"
    user.first_name = "Sergei"
    user.last_name = "V"
    user.language_code = "ru"
    user.is_bot = False
    user.is_premium = True
    user.role = 1
    return user


async def get_admin(
    db: DbDep,
    authorization: Annotated[str | None, Header()] = None,
) -> object:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("type") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    admin_id = int(payload.get("sub", 0))
    repo = AdminRepository(db)
    admin = await repo.get_by_id(admin_id)
    if not admin:
        raise HTTPException(status_code=401, detail="Admin not found")
    return admin


CurrentUser = Annotated[User, Depends(get_current_user)]
MiniappUser = Annotated[User, Depends(get_miniapp_user)]
AdminUser = Annotated[object, Depends(get_admin)]
