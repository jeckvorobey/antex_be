"""SSE and Redis Pub/Sub realtime transport for manager chat."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from app.core.redis import redis_client
from app.models.user import User

logger = logging.getLogger(__name__)

REALTIME_CHANNEL = "antex:manager:chat:events"
PRESENCE_PREFIX = "antex:manager:chat:presence:"
VIEWING_PREFIX = "antex:manager:chat:viewing:"
PRESENCE_TTL_SECONDS = 45
REALTIME_QUEUE_MAXSIZE = 100


@dataclass(slots=True)
class ManagerRealtimeConnection:
    manager_id: int
    connection_id: str
    events: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=REALTIME_QUEUE_MAXSIZE)
    )


class ManagerRealtimeHub:
    """Fan out Redis events to local manager SSE connections."""

    def __init__(self) -> None:
        self._connections: dict[int, dict[str, ManagerRealtimeConnection]] = {}
        self._listener_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._listen(), name="manager-chat-realtime")

    async def stop(self) -> None:
        task, self._listener_task = self._listener_task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        connections = [item for group in self._connections.values() for item in group.values()]
        self._connections.clear()
        for connection in connections:
            await self._delete_presence(connection.manager_id, connection.connection_id)

    async def register(self, manager_id: int, connection_id: str) -> ManagerRealtimeConnection:
        connection = ManagerRealtimeConnection(manager_id, connection_id)
        self._connections.setdefault(manager_id, {})[connection_id] = connection
        await self.refresh_presence(manager_id, connection_id)
        return connection

    async def unregister(self, manager_id: int, connection_id: str) -> None:
        group = self._connections.get(manager_id)
        if group is not None:
            group.pop(connection_id, None)
            if not group:
                self._connections.pop(manager_id, None)
        await self._delete_presence(manager_id, connection_id)

    async def _delete_presence(self, manager_id: int, connection_id: str) -> None:
        await redis_client.delete(f"{PRESENCE_PREFIX}{manager_id}:{connection_id}")
        await redis_client.delete(f"{VIEWING_PREFIX}{manager_id}:{connection_id}")

    async def refresh_presence(self, manager_id: int, connection_id: str) -> None:
        await redis_client.set(
            f"{PRESENCE_PREFIX}{manager_id}:{connection_id}", "1", ex=PRESENCE_TTL_SECONDS
        )
        await redis_client.expire(
            f"{VIEWING_PREFIX}{manager_id}:{connection_id}", PRESENCE_TTL_SECONDS
        )

    async def set_viewing(
        self, manager_id: int, connection_id: str, conversation_id: int | None
    ) -> bool:
        if not await redis_client.exists(f"{PRESENCE_PREFIX}{manager_id}:{connection_id}"):
            return False
        key = f"{VIEWING_PREFIX}{manager_id}:{connection_id}"
        if conversation_id is None:
            await redis_client.delete(key)
        else:
            await redis_client.set(key, str(conversation_id), ex=PRESENCE_TTL_SECONDS)
        return True

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
        self, event_type: str, payload: dict[str, Any], *, manager_id: int | None = None
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
            connections = [item for group in self._connections.values() for item in group.values()]
        else:
            connections = list(self._connections.get(int(manager_id), {}).values())
        for connection in connections:
            try:
                connection.events.put_nowait(envelope)
            except asyncio.QueueFull:
                connection.events = asyncio.Queue(maxsize=REALTIME_QUEUE_MAXSIZE)
                connection.events.put_nowait(
                    {
                        "type": "manager.refresh",
                        "payload": {"reason": "realtime.buffer.overflow"},
                        "managerId": connection.manager_id,
                    }
                )


manager_realtime_hub = ManagerRealtimeHub()


async def is_manager_miniapp_open(manager: User | None) -> bool:
    """Проверяет роль и наличие активного SSE stream менеджера."""
    if manager is None or not manager.isManager():
        return False
    try:
        return await manager_realtime_hub.is_online(manager.id)
    except Exception:
        logger.exception("Failed to read manager Mini App presence")
        return False


async def trigger_manager_refresh(manager: User | None, reason: str) -> bool:
    """Будит открытый manager Mini App без передачи бизнес-DTO в realtime."""
    if not await is_manager_miniapp_open(manager):
        return False
    await manager_realtime_hub.publish("manager.refresh", {"reason": reason}, manager_id=manager.id)
    return True
