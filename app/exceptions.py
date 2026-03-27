"""Кастомные исключения AntEx."""

from __future__ import annotations

from typing import Any


class AntExException(Exception):
    def __init__(
        self,
        message: str,
        code: str = "ANTEX_ERROR",
        status_code: int = 400,
        params: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.params = params or {}
        super().__init__(message)
