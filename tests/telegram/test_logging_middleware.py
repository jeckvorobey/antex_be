"""Тесты logging middleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.telegram.middlewares.logging import LoggingMiddleware


@pytest.mark.asyncio
async def test_logging_middleware_calls_next_handler() -> None:
    middleware = LoggingMiddleware()
    handler = AsyncMock(return_value="ok")
    event = object()
    data = {
        "event_from_user": SimpleNamespace(id=1, username="tester"),
        "event_update": object(),
    }

    result = await middleware(handler, event, data)

    assert result == "ok"
    handler.assert_awaited_once_with(event, data)
