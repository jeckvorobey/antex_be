"""Тесты user service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.telegram.services import user_service


@pytest.mark.asyncio
async def test_check_user_passes_tg_fields_to_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    expected_user = SimpleNamespace(id=1)

    class DummyRepo:
        def __init__(self, db) -> None:
            del db

        async def find_or_create(self, tg_id: int, **defaults: object):
            captured["tg_id"] = tg_id
            captured["defaults"] = defaults
            return expected_user, True

    tg_user = SimpleNamespace(
        id=1,
        username="tester",
        first_name="Serg",
        last_name="K",
        language_code="ru",
        is_bot=False,
        is_premium=True,
    )

    monkeypatch.setattr(user_service, "UserRepository", DummyRepo)

    user, created = await user_service.check_user(object(), tg_user)

    assert user is expected_user
    assert created is True
    assert captured["tg_id"] == 1
    assert captured["defaults"]["chatId"] == 1
