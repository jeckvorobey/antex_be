"""WebSocket and Redis Pub/Sub realtime transport for manager chat."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import suppress
from typing import Any

from fastapi import WebSocket

from app.core.redis import redis_client

logger = logging.getLogger(__name__)

REALTIME_CHANNEL = "antex:manager:chat:events"
SOCKET_TICKET_PREFIX = "antex:manager:chat:ticket:"
PRESENCE_PREFIX = "antex:manager:chat:presence:"
VIEWING_PREFIX = "antex:manager:chat:viewing:"
SOCKET_TICKET_TTL_SECONDS = 30
PRESENCE_TTL_SECONDS = 45


class ManagerRealtimeHub:
    """Fan out Redis events to local manager WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[int, set[WebSocket]] = {}
        self._listener_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._listener_task is not None and not self._listener_task.done():
            return
        self._listener_task = asyncio.create_task(self._listen(), name="manager-chat-realtime")

    async def stop(self) -> None:
        task = self._listener_task
        self._listener_task = None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        for sockets in list(self._connections.values()):
            for websocket in list(sockets):
                with suppress(Exception):
                    await websocket.close(code=1001)
        self._connections.clear()

    async def issue_ticket(self, manager_id: int) -> str:
        ticket = secrets.token_urlsafe(32)
        await redis_client.set(
            f"{SOCKET_TICKET_PREFIX}{ticket}",
            str(manager_id),
            ex=SOCKET_TICKET_TTL_SECONDS,
        )
        return ticket

    async def consume_ticket(self, ticket: str) -> int | None:
        value = await redis_client.getdel(f"{SOCKET_TICKET_PREFIX}{ticket}")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def register(self, manager_id: int, websocket: WebSocket, connection_id: str) -> None:
        self._connections.setdefault(manager_id, set()).add(websocket)
        await self.refresh_presence(manager_id, connection_id)

    async def unregister(self, manager_id: int, websocket: WebSocket, connection_id: str) -> None:
        sockets = self._connections.get(manager_id)
        if sockets is not None:
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(manager_id, None)
        await redis_client.delete(f"{PRESENCE_PREFIX}{manager_id}:{connection_id}")
        await redis_client.delete(f"{VIEWING_PREFIX}{manager_id}:{connection_id}")

    async def refresh_presence(self, manager_id: int, connection_id: str) -> None:
        await redis_client.set(
            f"{PRESENCE_PREFIX}{manager_id}:{connection_id}",
            "1",
            ex=PRESENCE_TTL_SECONDS,
        )
        await redis_client.expire(
            f"{VIEWING_PREFIX}{manager_id}:{connection_id}",
            PRESENCE_TTL_SECONDS,
        )

    async def set_viewing(
        self,
        manager_id: int,
        connection_id: str,
        conversation_id: int | None,
    ) -> None:
        key = f"{VIEWING_PREFIX}{manager_id}:{connection_id}"
        if conversation_id is None:
            await redis_client.delete(key)
            return
        await redis_client.set(
            key,
            str(conversation_id),
            ex=PRESENCE_TTL_SECONDS,
        )

    async def is_viewing(self, manager_id: int, conversation_id: int) -> bool:
        async for key in redis_client.scan_iter(match=f"{VIEWING_PREFIX}{manager_id}:*"):
            value = await redis_client.get(key)
            try:
                if value is not None and int(value) == conversation_id:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    async def is_online(self, manager_id: int) -> bool:
        async for _key in redis_client.scan_iter(match=f"{PRESENCE_PREFIX}{manager_id}:*"):
            return True
        return False

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        manager_id: int | None = None,
    ) -> None:
        envelope = {"type": event_type, "payload": payload, "managerId": manager_id}
        try:
            await redis_client.publish(REALTIME_CHANNEL, json.dumps(envelope, default=str))
        except Exception:
            logger.exception("Manager realtime publish failed: event=%s", event_type)

    async def _listen(self) -> None:
        while True:
            pubsub = redis_client.pubsub()
            try:
                await pubsub.subscribe(REALTIME_CHANNEL)
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        envelope = json.loads(message["data"])
                    except (TypeError, ValueError, json.JSONDecodeError):
                        logger.warning("Ignoring malformed manager realtime event")
                        continue
                    await self._broadcast_local(envelope)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Manager realtime subscriber failed; retrying")
                await asyncio.sleep(1)
            finally:
                with suppress(Exception):
                    await pubsub.aclose()

    async def _broadcast_local(self, envelope: dict[str, Any]) -> None:
        manager_id = envelope.get("managerId")
        if manager_id is None:
            sockets = [ws for group in self._connections.values() for ws in group]
        else:
            sockets = list(self._connections.get(int(manager_id), set()))
        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(envelope)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            for key, group in list(self._connections.items()):
                group.discard(websocket)
                if not group:
                    self._connections.pop(key, None)


manager_realtime_hub = ManagerRealtimeHub()
