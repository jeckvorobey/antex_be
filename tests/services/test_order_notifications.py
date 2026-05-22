from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.order_notifications import send_or_replace_user_status_message


class _FakeBot:
    def __init__(self) -> None:
        self.deleted: list[tuple[int, int]] = []
        self.sent: list[dict[str, object]] = []

    async def delete_message(self, chat_id: int, message_id: int) -> None:
        self.deleted.append((chat_id, message_id))

    async def send_message(self, chat_id: int, text: str, reply_markup=None):
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=88)


@pytest.mark.asyncio
async def test_user_status_message_replaces_previous_message() -> None:
    bot = _FakeBot()
    order = SimpleNamespace(userNotificationMessageId=77)

    new_message_id = await send_or_replace_user_status_message(
        bot=bot,
        chat_id=700002,
        order=order,
        text="updated",
        reply_markup=None,
    )

    assert bot.deleted == [(700002, 77)]
    assert bot.sent == [{"chat_id": 700002, "text": "updated", "reply_markup": None}]
    assert new_message_id == 88
    assert order.userNotificationMessageId == 88
