"""ASGI-ограничение размера JSON request body до полного разбора."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class JsonBodyLimitMiddleware:
    """Отклоняет oversized JSON, не затрагивая raw attachment streams."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _is_json_request(scope):
            await self.app(scope, receive, send)
            return

        content_length = _content_length(scope)
        if content_length is not None and content_length > self.max_bytes:
            await self._reject(scope, receive, send)
            return

        received_bytes = 0
        buffered_messages: list[Message] = []
        while True:
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                buffered_messages.append(message)
                if not message.get("more_body", False):
                    break
            else:
                buffered_messages.append(message)
                break

        async def receive_buffered() -> Message:
            if buffered_messages:
                return buffered_messages.pop(0)
            return await receive()

        await self.app(scope, receive_buffered, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "JSON body exceeds 1 MiB limit"},
        )
        await response(scope, receive, send)


def _is_json_request(scope: Scope) -> bool:
    for name, value in scope.get("headers", []):
        if name.lower() != b"content-type":
            continue
        media_type = value.decode("latin-1").split(";", 1)[0].strip().lower()
        return media_type == "application/json" or media_type.endswith("+json")
    return False


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() != b"content-length":
            continue
        try:
            length = int(value)
        except ValueError:
            return None
        return max(length, 0)
    return None
