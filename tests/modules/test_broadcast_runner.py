from __future__ import annotations

import asyncio

import pytest

from app.modules.broadcasts.audience import BroadcastRecipient
from app.modules.broadcasts.runner import deliver_recipients


class FakeBroadcastSender:
    def __init__(self) -> None:
        self.chat_ids: list[int] = []

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        button_text: str | None,
        button_url: str | None,
        allow_paid_broadcast: bool,
    ) -> None:
        del text, button_text, button_url, allow_paid_broadcast
        self.chat_ids.append(chat_id)


@pytest.mark.asyncio
async def test_deliver_recipients_sends_all_recipients_with_multiple_workers() -> None:
    sender = FakeBroadcastSender()
    recipients = [
        BroadcastRecipient(user_id=1, chat_id=101),
        BroadcastRecipient(user_id=2, chat_id=102),
        BroadcastRecipient(user_id=3, chat_id=103),
    ]
    progress_updates: list[tuple[int, int]] = []

    async def progress_callback(success_count: int, failed_count: int) -> None:
        progress_updates.append((success_count, failed_count))

    result = await asyncio.wait_for(
        deliver_recipients(
            recipients=recipients,
            sender=sender,
            text="Новости AntEx",
            text_format="plain",
            button_text=None,
            button_url=None,
            allow_paid_broadcast=False,
            target_rps=28,
            worker_count=8,
            progress_callback=progress_callback,
        ),
        timeout=0.5,
    )

    assert result == (3, 0)
    assert sorted(sender.chat_ids) == [101, 102, 103]
    assert progress_updates[-1] == (3, 0)
