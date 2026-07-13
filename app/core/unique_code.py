"""Безопасная генерация уникальных кодов."""
# ruff: noqa: RUF001

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from app.exceptions import AntExException


async def generate_unique_code(
    *,
    length: int,
    alphabet: str,
    exists: Callable[[str], Awaitable[bool]],
    max_attempts: int = 10,
) -> str:
    """Создает криптографический код и ограниченно повторяет collision."""
    if length <= 0 or not alphabet or max_attempts <= 0:
        raise ValueError("length, alphabet and max_attempts must be positive")

    for _ in range(max_attempts):
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if not await exists(candidate):
            return candidate

    raise AntExException(
        "Не удалось сгенерировать уникальный код",
        code="UNIQUE_CODE_EXHAUSTED",
        status_code=503,
    )
