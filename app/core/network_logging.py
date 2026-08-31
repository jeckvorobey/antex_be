"""Безопасный журнал входящих и исходящих сетевых операций."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from starlette.datastructures import MutableHeaders

network_logger = logging.getLogger("antex.network")
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$", re.ASCII)
_SAFE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$", re.ASCII)
_NETWORK_PROVIDERS = frozenset({"currencybeacon", "frankfurter", "telegram"})


def _request_id(headers: list[tuple[bytes, bytes]]) -> str:
    for name, value in headers:
        if name.lower() == b"x-request-id":
            candidate = value.decode("ascii", errors="ignore")
            if _REQUEST_ID_PATTERN.fullmatch(candidate):
                return candidate
            break
    return str(uuid4())


def _content_length(headers: list[tuple[bytes, bytes]]) -> int | None:
    for name, value in headers:
        if name.lower() == b"content-length":
            try:
                length = int(value)
            except ValueError:
                return None
            return length if length >= 0 else None
    return None


def emit_network_event(event: dict[str, object]) -> None:
    """Записывает заранее очищенное событие, не влияя на основной flow."""
    try:
        network_logger.info("network event", extra={"network_event": event})
    except Exception:
        return


def emit_outbound_network_event(
    *,
    provider: str,
    operation: str,
    status: int | None,
    duration_ms: float,
    retry_count: int = 0,
    error: BaseException | None = None,
) -> None:
    """Пишет outbound metadata без URL, credentials и transport payload."""
    if provider not in _NETWORK_PROVIDERS or not _SAFE_NAME_PATTERN.fullmatch(operation):
        return
    error_class = type(error).__name__ if error is not None else None
    if error_class is not None and not _SAFE_NAME_PATTERN.fullmatch(error_class):
        error_class = "NetworkError"
    emit_network_event(
        {
            "direction": "outbound",
            "provider": provider,
            "operation": operation,
            "status": status,
            "duration_ms": round(max(duration_ms, 0), 3),
            "retry_count": max(retry_count, 0),
            "error_class": error_class,
        }
    )


class NetworkLoggingMiddleware:
    """Pure-ASGI middleware без чтения payload, headers или query values."""

    def __init__(self, app: Callable[..., Awaitable[None]]) -> None:
        self.app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        request_id = _request_id(scope.get("headers", []))
        declared_bytes_in = _content_length(scope.get("headers", []))
        bytes_in = 0
        bytes_out = 0
        streaming = False
        status = 500

        async def counted_receive() -> dict[str, Any]:
            nonlocal bytes_in
            message = await receive()
            if message["type"] == "http.request":
                bytes_in += len(message.get("body", b""))
            return message

        async def counted_send(message: dict[str, Any]) -> None:
            nonlocal bytes_out, status, streaming
            if message["type"] == "http.response.start":
                status = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            elif message["type"] == "http.response.body":
                bytes_out += len(message.get("body", b""))
                streaming = streaming or bool(message.get("more_body"))
            await send(message)

        try:
            await self.app(scope, counted_receive, counted_send)
        finally:
            route = scope.get("route")
            route_template = getattr(route, "path", "<unmatched>")
            emit_network_event(
                {
                    "direction": "inbound",
                    "request_id": request_id,
                    "method": scope.get("method", "UNKNOWN"),
                    "route": route_template,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "bytes_in": bytes_in or declared_bytes_in,
                    "bytes_out": None if streaming else bytes_out,
                }
            )
