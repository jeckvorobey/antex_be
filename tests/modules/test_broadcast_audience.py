from __future__ import annotations

import pytest

from app.models.user import User
from app.modules.broadcasts.audience import TelegramUserAudienceProvider


@pytest.mark.asyncio
async def test_broadcast_audience_returns_real_users_without_special_guest_filter(
    db_session,
) -> None:
    db_session.add_all(
        [
            User(telegram_id=111, username="first", first_name="First"),
            User(telegram_id=222, username="second", first_name="Second"),
            User(telegram_id=None, username="without_tg", first_name="No Telegram"),
        ]
    )
    await db_session.flush()

    recipients = await TelegramUserAudienceProvider(db_session).list_recipients()

    assert [(recipient.user_id, recipient.chat_id) for recipient in recipients] == [
        (1, 111),
        (2, 222),
    ]


@pytest.mark.asyncio
async def test_broadcast_audience_can_stream_recipients_in_chunks(
    db_session,
) -> None:
    db_session.add_all(
        [
            User(telegram_id=111, username="first", first_name="First"),
            User(telegram_id=222, username="second", first_name="Second"),
            User(telegram_id=333, username="third", first_name="Third"),
        ]
    )
    await db_session.flush()

    provider = TelegramUserAudienceProvider(db_session)
    recipients = [
        (recipient.user_id, recipient.chat_id)
        async for recipient in provider.iter_recipients(batch_size=2)
    ]

    assert recipients == [(1, 111), (2, 222), (3, 333)]
    assert await provider.count_recipients() == 3
