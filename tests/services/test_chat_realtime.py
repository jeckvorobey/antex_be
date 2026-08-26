from __future__ import annotations

import asyncio

from app.services.chat_realtime import ManagerRealtimeHub


class FakePubSub:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self.messages: asyncio.Queue[dict[str, object]] = asyncio.Queue()

    async def subscribe(self, _channel: str) -> None:
        self.redis.subscribers.add(self)
        self.redis.subscribers_changed.set()

    async def listen(self):
        while True:
            yield await self.messages.get()

    async def aclose(self) -> None:
        self.redis.subscribers.discard(self)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.subscribers: set[FakePubSub] = set()
        self.subscribers_changed = asyncio.Event()

    async def set(self, key: str, value: str, **_kwargs) -> bool:
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    async def exists(self, key: str) -> int:
        return int(key in self.values)

    async def expire(self, key: str, _ttl: int) -> bool:
        return key in self.values

    async def scan_iter(self, *, match: str):
        prefix = match.removesuffix("*")
        for key in list(self.values):
            if key.startswith(prefix):
                yield key

    def pubsub(self) -> FakePubSub:
        return FakePubSub(self)

    async def publish(self, _channel: str, data: str) -> int:
        for subscriber in list(self.subscribers):
            subscriber.messages.put_nowait({"type": "message", "data": data})
        return len(self.subscribers)

    async def wait_for_subscribers(self, count: int) -> None:
        while len(self.subscribers) < count:
            self.subscribers_changed.clear()
            await asyncio.wait_for(self.subscribers_changed.wait(), timeout=1)


async def test_sse_connection_receives_published_event(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    hub = ManagerRealtimeHub()

    connection = await hub.register(42, "connection-a")
    await hub._broadcast_local({"type": "chat.unread.updated", "payload": {"unreadTotal": 2}})

    assert await connection.events.get() == {
        "type": "chat.unread.updated",
        "payload": {"unreadTotal": 2},
    }


async def test_redis_pubsub_fans_out_event_between_backend_instances(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    first_hub = ManagerRealtimeHub()
    second_hub = ManagerRealtimeHub()
    first_connection = await first_hub.register(42, "connection-a")
    second_connection = await second_hub.register(42, "connection-b")

    await first_hub.start()
    await second_hub.start()
    try:
        await fake.wait_for_subscribers(2)
        await first_hub.publish(
            "manager.refresh",
            {"reason": "chat.message.created"},
            manager_id=42,
        )

        expected = {
            "type": "manager.refresh",
            "payload": {"reason": "chat.message.created"},
            "managerId": 42,
        }
        assert await asyncio.wait_for(first_connection.events.get(), timeout=1) == expected
        assert await asyncio.wait_for(second_connection.events.get(), timeout=1) == expected
    finally:
        await first_hub.stop()
        await second_hub.stop()


async def test_slow_sse_connection_has_bounded_buffer_and_reconciles(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    hub = ManagerRealtimeHub()
    connection = await hub.register(42, "connection-a")

    for sequence in range(300):
        await hub._broadcast_local(
            {
                "type": "chat.message.updated",
                "payload": {"sequence": sequence},
                "managerId": 42,
            }
        )

    assert connection.events.qsize() <= 100
    assert await connection.events.get() == {
        "type": "manager.refresh",
        "payload": {"reason": "realtime.buffer.overflow"},
        "managerId": 42,
    }


async def test_presence_and_viewing_are_separate(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    hub = ManagerRealtimeHub()

    await hub.register(7, "connection-a")
    await hub.set_viewing(7, "connection-a", 99)

    assert await hub.is_online(7) is True
    assert await hub.is_viewing(7, 99) is True
    assert await hub.is_viewing(7, 100) is False

    await hub.set_viewing(7, "connection-a", None)
    assert await hub.is_viewing(7, 99) is False


async def test_presence_is_independent_per_connection_across_instances(monkeypatch) -> None:
    """Disconnect одного SSE stream не удаляет presence второго экземпляра."""
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    first_hub = ManagerRealtimeHub()
    second_hub = ManagerRealtimeHub()
    await first_hub.register(8, "connection-a")
    await second_hub.register(8, "connection-b")

    await second_hub.unregister(8, "connection-b")

    assert await first_hub.is_online(8) is True
    await first_hub.unregister(8, "connection-a")
    assert await second_hub.is_online(8) is False


async def test_viewing_is_independent_per_connection_across_instances(monkeypatch) -> None:
    """Каждый SSE stream хранит собственную открытую беседу в Redis."""
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    first_hub = ManagerRealtimeHub()
    second_hub = ManagerRealtimeHub()

    await first_hub.register(9, "connection-a")
    await second_hub.register(9, "connection-b")
    assert await first_hub.set_viewing(9, "connection-a", 101) is True
    assert await second_hub.set_viewing(9, "connection-b", 202) is True

    assert await first_hub.is_viewing(9, 101) is True
    assert await second_hub.is_viewing(9, 202) is True

    assert await second_hub.set_viewing(9, "connection-b", None) is True
    assert await first_hub.is_viewing(9, 101) is True
    assert await second_hub.is_viewing(9, 202) is False


async def test_viewing_rejects_unknown_sse_connection(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    hub = ManagerRealtimeHub()

    assert await hub.set_viewing(9, "unknown", 101) is False
