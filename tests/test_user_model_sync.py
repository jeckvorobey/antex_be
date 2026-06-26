from __future__ import annotations

from aiogram.types import User as TgUser
from sqlalchemy.exc import IntegrityError

from app.enums.user import UserRole, get_role_title, has_admin_access, has_operator_access
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.user import build_user_out
from app.services.auth import resolve_trusted_contact, telegram_auth
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
        photo_url="https://t.me/i/userpic/320/old.jpg",
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
        photo_url=None,
    )

    assert created is False
    assert same_user.id == user.id
    assert same_user.username == "new_name"
    assert same_user.first_name == "New"
    assert same_user.language_code == "ru"
    assert same_user.is_premium is True
    assert same_user.photo_url is None
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


async def test_telegram_auth_persists_updates_and_clears_photo_url(
    monkeypatch,
    db_session,
) -> None:
    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "user": (
                '{"id": 654321, "username": "photo_user", "first_name": "Photo", '
                '"last_name": "User", "language_code": "ru", "is_bot": false, '
                '"is_premium": false, "photo_url": "https://t.me/i/userpic/320/old.jpg"}'
            )
        },
    )
    monkeypatch.setattr(
        "app.services.auth.create_access_token",
        lambda data: f"token-{data['sub']}",
    )

    await telegram_auth(db_session, "init-data")
    user = await UserRepository(db_session).get_one(1)
    assert user is not None
    assert user.photo_url == "https://t.me/i/userpic/320/old.jpg"

    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "user": (
                '{"id": 654321, "username": "photo_user", "first_name": "Photo", '
                '"last_name": "User", "language_code": "ru", "is_bot": false, '
                '"is_premium": true, "photo_url": "https://t.me/i/userpic/320/new.jpg"}'
            )
        },
    )

    await telegram_auth(db_session, "init-data")
    refreshed_user = await UserRepository(db_session).get_one(1)
    assert refreshed_user is not None
    assert refreshed_user.photo_url == "https://t.me/i/userpic/320/new.jpg"

    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "user": (
                '{"id": 654321, "username": "photo_user", "first_name": "Photo", '
                '"last_name": "User", "language_code": "ru", "is_bot": false, '
                '"is_premium": false}'
            )
        },
    )

    await telegram_auth(db_session, "init-data")
    cleared_user = await UserRepository(db_session).get_one(1)
    assert cleared_user is not None
    assert cleared_user.photo_url is None


async def test_telegram_auth_binds_existing_user_from_referral_start_param(
    monkeypatch,
    db_session,
) -> None:
    referrer = User(telegram_id=2001, username="auth_referrer", referral_code="A7kP2mX9")
    existing_user = User(telegram_id=2002, username="auth_referred")
    db_session.add_all([referrer, existing_user])
    await db_session.flush()

    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "start_param": "ref_A7kP2mX9",
            "user": (
                '{"id": 2002, "username": "auth_referred", "first_name": "Linked", '
                '"last_name": "User", "language_code": "ru", "is_bot": false, '
                '"is_premium": false}'
            ),
        },
    )
    monkeypatch.setattr(
        "app.services.auth.create_access_token",
        lambda data: f"token-{data['sub']}",
    )

    await telegram_auth(db_session, "init-data")

    await db_session.refresh(existing_user)
    assert existing_user.referred_by == referrer.id


async def test_telegram_auth_does_not_rewrite_existing_referral_from_start_param(
    monkeypatch,
    db_session,
) -> None:
    original_referrer = User(
        telegram_id=2011,
        username="auth_referrer_one",
        referral_code="A7kP2mX9",
    )
    new_referrer = User(
        telegram_id=2012,
        username="auth_referrer_two",
        referral_code="hF84LmQz",
    )
    existing_user = User(telegram_id=2013, username="auth_already_referred")
    db_session.add_all([original_referrer, new_referrer, existing_user])
    await db_session.flush()
    existing_user.referred_by = original_referrer.id
    await db_session.flush()

    monkeypatch.setattr(
        "app.services.auth.validate_telegram_init_data",
        lambda _: {
            "start_param": "ref_hF84LmQz",
            "user": (
                '{"id": 2013, "username": "auth_already_referred", '
                '"first_name": "Linked", "last_name": "User", "language_code": "ru", '
                '"is_bot": false, "is_premium": false}'
            ),
        },
    )
    monkeypatch.setattr(
        "app.services.auth.create_access_token",
        lambda data: f"token-{data['sub']}",
    )

    await telegram_auth(db_session, "init-data")

    await db_session.refresh(existing_user)
    assert existing_user.referred_by == original_referrer.id


async def test_users_username_is_unique(db_session) -> None:
    first_user = User(
        telegram_id=1001,
        username="unique_name",
        first_name="First",
        role=UserRole.USER,
    )
    second_user = User(
        telegram_id=1002,
        username="unique_name",
        first_name="Second",
        role=UserRole.USER,
    )

    db_session.add(first_user)
    await db_session.flush()

    db_session.add(second_user)

    try:
        await db_session.flush()
    except IntegrityError:
        await db_session.rollback()
    else:
        raise AssertionError("Duplicate username must violate a unique constraint")


async def test_resolve_trusted_contact_falls_back_to_phone(db_session) -> None:
    repo = UserRepository(db_session)
    user, _ = await repo.find_or_create(
        999,
        username=None,
        first_name="Phone",
        last_name="Only",
        language_code="ru",
        is_bot=False,
        is_premium=False,
    )

    missing_contact = resolve_trusted_contact(user)
    assert missing_contact.ready is False
    assert missing_contact.contact is None
    assert missing_contact.source is None

    updated_user = await repo.set_phone(user.id, "+79991234567")
    assert updated_user is not None

    phone_contact = resolve_trusted_contact(updated_user)
    assert phone_contact.ready is True
    assert phone_contact.contact == "+79991234567"
    assert phone_contact.source == "phone"


def test_user_role_helpers_and_serializer() -> None:
    assert UserRole.USER == 9
    assert get_role_title(UserRole.USER) == "Пользователь"
    assert get_role_title(UserRole.MANAGER) == "Менеджер"
    assert get_role_title(1) == "Менеджер"
    assert get_role_title(8) == "Роль 8"
    assert has_operator_access(UserRole.USER) is False
    assert has_operator_access(8) is False
    assert has_operator_access(UserRole.MANAGER) is True
    assert has_operator_access(1) is True
    assert has_admin_access(UserRole.MANAGER) is True
    assert has_admin_access(1) is True

    fake_user = type("FakeUser", (), {})()
    fake_user.id = 1
    fake_user.telegram_id = 777
    fake_user.username = "user"
    fake_user.first_name = "Test"
    fake_user.last_name = "User"
    fake_user.language_code = "ru"
    fake_user.language_code_app = "ru"
    fake_user.photo_url = "https://t.me/i/userpic/320/user.jpg"
    fake_user.phone = "+79991234567"
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

    fake_user.role = 1
    legacy_manager_out = build_user_out(fake_user)
    assert legacy_manager_out.role == 2
    assert legacy_manager_out.role_name == "Менеджер"
    assert user_out.photo_url == "https://t.me/i/userpic/320/user.jpg"
    assert user_out.phone == "+79991234567"
    assert user_out.trusted_contact == "user"
    assert user_out.trusted_contact_source == "username"
    assert user_out.trusted_contact_ready is True
