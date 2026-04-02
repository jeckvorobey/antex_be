"""Enums для пользователей."""

from __future__ import annotations

from enum import IntEnum


class UserRole(IntEnum):
    USER = 1
    MANAGER = 2
    OPERATOR = 2
    ADMIN = 3
