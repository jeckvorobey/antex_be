from __future__ import annotations

from aiogram.types import User as TgUser

from app.enums.user import UserRole, get_role_title, has_admin_access, has_operator_access
from app.repositories.user import UserRepository
from app.schemas.user import build_user_out
from app.services.auth import telegram_auth
from app.telegram.services.user_service import check_user


async def test_find_or_create_updates_existing_user_without_chat_id(db_session) -> None:
    repo = UserRepository(db_session)

    user, created = await repo.find_or_create(
        777,
        username="old_name",
        first_name="Old",
        last_name="Name",
        language_code="en",
        is_bot=False,
        is_premium=False,
    )
    assert created is True
    assert user.role == UserRole.USER
    assert user.language_code_app == "ru"

    same_user, created = await repo.find_or_create(
        777,
        username="new_name",
        first_name="New",
        last_name="Name",
        language_code="ru",
        is_bot=False,
        is_premium=True,
    )

    assert created is False
    assert same_user.id == user.id
    assert same_user.username == "new_name"
    assert same_user.first_name == "New"
    assert same_user.language_code == "ru"
    assert same_user.is_premium is True
    assert not hasattr(same_user, "chatId")


async def test_check_user_refreshes_user_from_start_command(db_session) -> None:
    tg_user = TgUser(
        id=555,
        is_bot=False,
        first_name="Initial",
        last_name="User",
        username="initial",
        language_code="en",
        is_premium=False,
    )
    user, created = await check_user(db_session, tg_user)
    assert created is True

    refreshed_tg_user = TgUser(
        id=555,
        is_bot=False,
        first_name="Updated",
        last_name="User",
        username="updated",
        language_code="ru",
        is_premium=True,
    )
    updated_user, created = await check_user(db_session, refreshed_tg_user)

    assert created is False
    assert updated_user.id == user.id
    assert updated_user.username == "updated"
    assert updated_user.first_name == "Updated"
    assert updated_user.language_code == "ru"
    assert updated_user.is_premium is True


async def test_telegram_auth_refreshes_existing_user(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "user": (
                '{"id": 123456, "username": "initial_user", "first_name": "Initial", '
                '"last_name": "User", "language_code": "en", "is_bot": false, '
                '"is_premium": false}'
            )
        },
    )
    monkeypatch.setattr(
        "app.services.auth.create_access_token",
        lambda data: f"token-{data['sub']}",
    )

    first_token = await telegram_auth(db_session, "init-data")
    assert first_token.access_token == "token-1"

    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "user": (
                '{"id": 123456, "username": "fresh_user", "first_name": "Fresh", '
                '"last_name": "User", "language_code": "ru", "is_bot": false, '
                '"is_premium": true}'
            )
        },
    )

    second_token = await telegram_auth(db_session, "init-data")
    assert second_token.access_token == "token-1"

    user = await UserRepository(db_session).get_one(1)
    assert user is not None
    assert user.username == "fresh_user"
    assert user.first_name == "Fresh"
    assert user.language_code == "ru"
    assert user.is_premium is True


def test_user_role_helpers_and_serializer() -> None:
    assert UserRole.USER == 9
    assert get_role_title(UserRole.USER) == "Пользователь"
    assert get_role_title(UserRole.MANAGER) == "Менеджер"
    assert get_role_title(UserRole.OPERATOR) == "Оператор"
    assert get_role_title(UserRole.ADMIN) == "Администратор"
    assert has_operator_access(UserRole.USER) is False
    assert has_operator_access(UserRole.OPERATOR) is True
    assert has_admin_access(UserRole.OPERATOR) is False
    assert has_admin_access(UserRole.ADMIN) is True

    fake_user = type("FakeUser", (), {})()
    fake_user.id = 1
    fake_user.telegram_id = 777
    fake_user.username = "user"
    fake_user.first_name = "Test"
    fake_user.last_name = "User"
    fake_user.language_code = "ru"
    fake_user.language_code_app = "ru"
    fake_user.is_bot = False
    fake_user.role = UserRole.USER
    fake_user.is_premium = False
    fake_user.city_id = None
    fake_user.city = None
    fake_user.createdAt = "2026-04-03T00:00:00+00:00"
    fake_user.updatedAt = "2026-04-03T00:00:00+00:00"

    user_out = build_user_out(fake_user)
    assert user_out.role == 9
    assert user_out.role_name == "Пользователь"
    assert user_out.language_code_app == "ru"
