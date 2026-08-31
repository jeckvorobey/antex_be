from __future__ import annotations

import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient

from app.core.network_logging import NetworkLoggingMiddleware, emit_outbound_network_event
from app.telegram.middlewares.network import TelegramNetworkMiddleware


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, object]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.events.append(record.network_event)


@pytest.fixture
def network_capture() -> _Capture:
    logger = logging.getLogger("antex.network")
    original_handlers = list(logger.handlers)
    original_propagate = logger.propagate
    original_disabled = logger.disabled
    original_global_disable = logging.root.manager.disable
    capture = _Capture()
    logger.handlers = [capture]
    logger.propagate = False
    logger.disabled = False
    logging.disable(logging.NOTSET)
    logger.setLevel(logging.INFO)
    try:
        yield capture
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate
        logger.disabled = original_disabled
        logging.disable(original_global_disable)


async def test_inbound_event_uses_route_template_and_omits_sensitive_request_data(
    network_capture: _Capture,
) -> None:
    app = FastAPI()
    app.add_middleware(NetworkLoggingMiddleware)

    @app.post("/items/{item_id}")
    async def item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/items/42?api_key=secret-query",
            headers={"Authorization": "Bearer secret-token", "X-Request-ID": "request_1234"},
            json={"password": "secret-body"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "request_1234"
    event = network_capture.events[-1]
    assert event == {
        "direction": "inbound",
        "request_id": "request_1234",
        "method": "POST",
        "route": "/items/{item_id}",
        "status": 200,
        "duration_ms": event["duration_ms"],
        "bytes_in": len(b'{"password":"secret-body"}'),
        "bytes_out": len(b'{"item_id":42}'),
    }
    assert "secret" not in json.dumps(event)


async def test_invalid_request_id_is_replaced_and_unmatched_route_is_bounded(
    network_capture: _Capture,
) -> None:
    app = FastAPI()
    app.add_middleware(NetworkLoggingMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/missing", headers={"X-Request-ID": "bad\nvalue"})

    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36
    assert network_capture.events[-1]["route"] == "<unmatched>"


def test_outbound_event_contains_only_safe_bounded_metadata(network_capture: _Capture) -> None:
    emit_outbound_network_event(
        provider="currencybeacon",
        operation="latest",
        status=200,
        duration_ms=12.5,
        retry_count=1,
        error=RuntimeError("api_key=secret-value"),
    )

    event = network_capture.events[-1]
    assert event == {
        "direction": "outbound",
        "provider": "currencybeacon",
        "operation": "latest",
        "status": 200,
        "duration_ms": 12.5,
        "retry_count": 1,
        "error_class": "RuntimeError",
    }
    assert "secret-value" not in json.dumps(event)


async def test_telegram_middleware_logs_method_name_without_payload(
    network_capture: _Capture,
) -> None:
    from aiogram.methods import SendMessage

    method = SendMessage(chat_id=123, text="private message text")

    async def make_request(bot: object, request: object) -> dict[str, bool]:
        del bot, request
        return {"ok": True}

    result = await TelegramNetworkMiddleware()(make_request, object(), method)

    assert result == {"ok": True}
    event = network_capture.events[-1]
    assert event["provider"] == "telegram"
    assert event["operation"] == "SendMessage"
    assert event["status"] == 200
    assert "private message text" not in json.dumps(event)


async def test_streaming_response_is_not_buffered_for_size(network_capture: _Capture) -> None:
    app = FastAPI()
    app.add_middleware(NetworkLoggingMiddleware)

    @app.get("/events")
    async def events() -> StreamingResponse:
        async def stream():
            yield b"data: ready\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/events")

    assert response.content == b"data: ready\n\n"
    assert network_capture.events[-1]["bytes_out"] is None


async def test_network_logger_failure_does_not_change_http_result(
    network_capture: _Capture, monkeypatch: pytest.MonkeyPatch
) -> None:
    del network_capture
    app = FastAPI()
    app.add_middleware(NetworkLoggingMiddleware)

    @app.get("/ok")
    async def ok() -> dict[str, bool]:
        return {"ok": True}

    monkeypatch.setattr("app.core.network_logging.network_logger.info", lambda *a, **k: 1 / 0)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ok")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_exception_is_recorded_as_500(network_capture: _Capture) -> None:
    app = FastAPI()
    app.add_middleware(NetworkLoggingMiddleware)

    @app.get("/broken")
    async def broken() -> None:
        raise RuntimeError("sensitive exception payload")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/broken")

    assert response.status_code == 500
    event = network_capture.events[-1]
    assert event["status"] == 500
    assert "sensitive exception payload" not in json.dumps(event)
