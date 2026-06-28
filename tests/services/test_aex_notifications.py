"""Тесты для AEX Telegram-уведомлений."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.aex_notifications import (
    _build_aex_notification_text,
    notify_aex_operation,
)


class TestBuildAexNotificationText:
    """Тесты построения текста уведомления."""

    def test_credit_notification_text(self) -> None:
        text = _build_aex_notification_text(
            operation_type="credit",
            amount=Decimal("100.50"),
            description="Бонус за регистрацию",
        )
        assert "Начисление AEX" in text
        assert "💰" in text
        assert "100.50 AEX" in text
        assert "Бонус за регистрацию" in text

    def test_debit_notification_text(self) -> None:
        text = _build_aex_notification_text(
            operation_type="debit",
            amount=Decimal("50"),
            description="Списание по запросу",
        )
        assert "Списание AEX" in text
        assert "💸" in text
        assert "50 AEX" in text
        assert "Списание по запросу" in text

    def test_notification_without_description(self) -> None:
        text = _build_aex_notification_text(
            operation_type="credit",
            amount=Decimal("100"),
        )
        assert "Начисление AEX" in text
        assert "100 AEX" in text
        assert "Описание" not in text


class TestNotifyAexOperation:
    """Тесты отправки уведомлений."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        return AsyncMock()

    @pytest.fixture
    def mock_user(self) -> MagicMock:
        user = MagicMock()
        user.telegram_id = 123456789
        return user

    async def test_sends_credit_notification(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        with (
            patch(
                "app.services.aex_notifications.UserRepository"
            ) as mock_repo_cls,
            patch("app.telegram.bot.bot") as mock_bot,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_one.return_value = mock_user
            mock_repo_cls.return_value = mock_repo

            await notify_aex_operation(
                mock_db,
                user_id=1,
                operation_type="credit",
                amount=Decimal("100"),
                description="Тест",
            )

            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args
            assert call_kwargs.kwargs["chat_id"] == 123456789
            assert "Начисление AEX" in call_kwargs.kwargs["text"]

    async def test_sends_debit_notification(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        with (
            patch(
                "app.services.aex_notifications.UserRepository"
            ) as mock_repo_cls,
            patch("app.telegram.bot.bot") as mock_bot,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_one.return_value = mock_user
            mock_repo_cls.return_value = mock_repo

            await notify_aex_operation(
                mock_db,
                user_id=1,
                operation_type="debit",
                amount=Decimal("50"),
                description="Списание",
            )

            mock_bot.send_message.assert_called_once()
            call_kwargs = mock_bot.send_message.call_args
            assert "Списание AEX" in call_kwargs.kwargs["text"]

    async def test_skips_when_user_not_found(self, mock_db: AsyncMock) -> None:
        with patch(
            "app.services.aex_notifications.UserRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_one.return_value = None
            mock_repo_cls.return_value = mock_repo

            # No exception expected
            await notify_aex_operation(
                mock_db,
                user_id=999,
                operation_type="credit",
                amount=Decimal("100"),
            )

    async def test_skips_when_no_telegram_id(
        self, mock_db: AsyncMock
    ) -> None:
        user_no_tg = MagicMock()
        user_no_tg.telegram_id = None

        with patch(
            "app.services.aex_notifications.UserRepository"
        ) as mock_repo_cls:
            mock_repo = AsyncMock()
            mock_repo.get_one.return_value = user_no_tg
            mock_repo_cls.return_value = mock_repo

            # No exception expected
            await notify_aex_operation(
                mock_db,
                user_id=1,
                operation_type="credit",
                amount=Decimal("100"),
            )

    async def test_skips_when_bot_not_initialized(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        with (
            patch(
                "app.services.aex_notifications.UserRepository"
            ) as mock_repo_cls,
            patch("app.telegram.bot.bot", None),
        ):
            mock_repo = AsyncMock()
            mock_repo.get_one.return_value = mock_user
            mock_repo_cls.return_value = mock_repo

            # No exception expected
            await notify_aex_operation(
                mock_db,
                user_id=1,
                operation_type="credit",
                amount=Decimal("100"),
            )

    async def test_handles_send_error_gracefully(
        self, mock_db: AsyncMock, mock_user: MagicMock
    ) -> None:
        with (
            patch(
                "app.services.aex_notifications.UserRepository"
            ) as mock_repo_cls,
        ):
            mock_repo = AsyncMock()
            mock_repo.get_one.return_value = mock_user
            mock_repo_cls.return_value = mock_repo

            mock_bot = AsyncMock()
            mock_bot.send_message.side_effect = Exception("Telegram error")

            with patch("app.telegram.bot.bot", mock_bot):
                # No exception expected - best-effort
                await notify_aex_operation(
                    mock_db,
                    user_id=1,
                    operation_type="credit",
                    amount=Decimal("100"),
                )
