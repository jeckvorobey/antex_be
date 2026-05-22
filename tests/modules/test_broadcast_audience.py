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
