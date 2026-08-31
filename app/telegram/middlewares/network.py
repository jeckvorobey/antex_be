"""Network journal middleware для aiogram transport session."""

from __future__ import annotations

import time
from typing import Any

from aiogram.client.session.middlewares.base import BaseRequestMiddleware

from app.core.network_logging import emit_outbound_network_event


class TelegramNetworkMiddleware(BaseRequestMiddleware):
    """Логирует только безопасное имя Telegram API method и результат transport."""

    async def __call__(self, make_request: Any, bot: Any, method: Any) -> Any:
        started = time.perf_counter()
        error: BaseException | None = None
        try:
            return await make_request(bot, method)
        except BaseException as exc:
            error = exc
            raise
        finally:
            emit_outbound_network_event(
                provider="telegram",
                operation=type(method).__name__,
                status=200 if error is None else None,
                duration_ms=(time.perf_counter() - started) * 1000,
                error=error,
            )
