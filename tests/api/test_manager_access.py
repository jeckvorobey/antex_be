from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.deps import get_manager_user
from app.enums.user import UserRole
from app.models.user import User


async def test_manager_dependency_rejects_regular_user() -> None:
    user = User(id=1, role=int(UserRole.USER))

    with pytest.raises(HTTPException) as exc_info:
        await get_manager_user(user)

    assert exc_info.value.status_code == 403


async def test_manager_dependency_accepts_manager() -> None:
    manager = User(id=2, role=int(UserRole.MANAGER))

    resolved = await get_manager_user(manager)

    assert resolved is manager
