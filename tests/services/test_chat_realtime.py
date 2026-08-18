from __future__ import annotations

from app.services.chat_realtime import ManagerRealtimeHub


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, **_kwargs) -> bool:
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)

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


async def test_socket_ticket_is_single_use(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    hub = ManagerRealtimeHub()

    ticket = await hub.issue_ticket(42)

    assert await hub.consume_ticket(ticket) == 42
    assert await hub.consume_ticket(ticket) is None


async def test_presence_and_viewing_are_separate(monkeypatch) -> None:
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    hub = ManagerRealtimeHub()

    await hub.refresh_presence(7, "connection-a")
    await hub.set_viewing(7, "connection-a", 99)

    assert await hub.is_online(7) is True
    assert await hub.is_viewing(7, 99) is True
    assert await hub.is_viewing(7, 100) is False

    await hub.set_viewing(7, "connection-a", None)
    assert await hub.is_viewing(7, 99) is False


async def test_presence_is_independent_per_connection_across_instances(monkeypatch) -> None:
    """Disconnect одного backend socket не удаляет presence второго экземпляра."""
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    first_hub = ManagerRealtimeHub()
    second_hub = ManagerRealtimeHub()
    first_socket = object()
    second_socket = object()

    await first_hub.register(8, first_socket, "connection-a")
    await second_hub.register(8, second_socket, "connection-b")

    await second_hub.unregister(8, second_socket, "connection-b")

    assert await first_hub.is_online(8) is True
    await first_hub.unregister(8, first_socket, "connection-a")
    assert await second_hub.is_online(8) is False


async def test_viewing_is_independent_per_connection_across_instances(monkeypatch) -> None:
    """Каждый backend socket хранит собственную открытую беседу в Redis."""
    fake = FakeRedis()
    monkeypatch.setattr("app.services.chat_realtime.redis_client", fake)
    first_hub = ManagerRealtimeHub()
    second_hub = ManagerRealtimeHub()

    await first_hub.set_viewing(9, "connection-a", 101)
    await second_hub.set_viewing(9, "connection-b", 202)

    assert await first_hub.is_viewing(9, 101) is True
    assert await second_hub.is_viewing(9, 202) is True

    await second_hub.set_viewing(9, "connection-b", None)
    assert await first_hub.is_viewing(9, 101) is True
    assert await second_hub.is_viewing(9, 202) is False
