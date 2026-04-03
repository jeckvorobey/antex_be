"""Enums для пользователей."""

from __future__ import annotations

from enum import IntEnum


class UserRole(IntEnum):
    USER = 9
    MANAGER = 2
    OPERATOR = 8
    ADMIN = 3


ROLE_TITLES: dict[int, str] = {
    UserRole.USER: "Пользователь",
    UserRole.MANAGER: "Менеджер",
    UserRole.OPERATOR: "Оператор",
    UserRole.ADMIN: "Администратор",
}

OPERATOR_ACCESS_ROLES = frozenset({UserRole.MANAGER, UserRole.OPERATOR, UserRole.ADMIN})
ADMIN_ACCESS_ROLES = frozenset({UserRole.ADMIN})


def get_role_title(role: int | UserRole) -> str:
    return ROLE_TITLES.get(int(role), f"Роль {int(role)}")


def has_operator_access(role: int | UserRole) -> bool:
    return int(role) in {int(item) for item in OPERATOR_ACCESS_ROLES}


def has_admin_access(role: int | UserRole) -> bool:
    return int(role) in {int(item) for item in ADMIN_ACCESS_ROLES}
