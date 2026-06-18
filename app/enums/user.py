"""Enums для пользователей."""

from __future__ import annotations

from enum import IntEnum


class UserRole(IntEnum):
    USER = 9
    MANAGER = 2


LEGACY_ADMIN_ROLE = 1
ASSIGNABLE_USER_ROLES = frozenset({UserRole.USER, UserRole.MANAGER})
OPERATOR_ACCESS_ROLES = frozenset({UserRole.MANAGER, LEGACY_ADMIN_ROLE})
ADMIN_ACCESS_ROLES = frozenset({UserRole.MANAGER, LEGACY_ADMIN_ROLE})

ROLE_TITLES: dict[int, str] = {
    int(UserRole.USER): "Пользователь",
    int(UserRole.MANAGER): "Менеджер",
    LEGACY_ADMIN_ROLE: "Менеджер",
}


def normalize_user_role(role: int | UserRole) -> int:
    value = int(role)
    if value == LEGACY_ADMIN_ROLE:
        return int(UserRole.MANAGER)
    return value


def is_assignable_user_role(role: int | UserRole) -> bool:
    return int(role) in {int(item) for item in ASSIGNABLE_USER_ROLES}


def get_role_title(role: int | UserRole) -> str:
    normalized_role = normalize_user_role(role)
    return ROLE_TITLES.get(normalized_role, f"Роль {normalized_role}")


def has_operator_access(role: int | UserRole) -> bool:
    return int(role) in {int(item) for item in OPERATOR_ACCESS_ROLES}


def has_admin_access(role: int | UserRole) -> bool:
    return int(role) in {int(item) for item in ADMIN_ACCESS_ROLES}
