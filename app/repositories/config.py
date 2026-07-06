"""Репозиторий конфигурации."""

from __future__ import annotations

from decimal import Decimal

from app.models.config import Config
from app.repositories.base import BaseRepository

CONFIG_ID = 1


class ConfigRepository(BaseRepository[Config]):
    model = Config

    async def get_or_create(self) -> Config:
        config = await self.session.get(Config, CONFIG_ID)
        if not config:
            config = Config(id=CONFIG_ID, enabled=True)
            self.session.add(config)
            await self.session.flush()
        return config

    async def toggle_enabled(self) -> Config:
        config = await self.get_or_create()
        config.enabled = not config.enabled
        await self.session.flush()
        return config

    async def set_enabled(self, enabled: bool) -> Config:
        config = await self.get_or_create()
        config.enabled = enabled
        await self.session.flush()
        return config

    async def update_referral_program(
        self,
        *,
        referral_percent: Decimal | None = None,
        referral_min_withdraw: Decimal | None = None,
        referral_max_withdraw: Decimal | None = None,
        aex_rate: Decimal | None = None,
        aex_withdraw_limit: Decimal | None = None,
        update_referral_max_withdraw: bool = False,
    ) -> Config:
        """Обновляет глобальные настройки referral/AEX program."""
        config = await self.get_or_create()
        if referral_percent is not None:
            config.referral_percent = referral_percent
        if referral_min_withdraw is not None:
            config.referral_min_withdraw = referral_min_withdraw
        if update_referral_max_withdraw:
            config.referral_max_withdraw = referral_max_withdraw
        if aex_rate is not None:
            config.aex_rate = aex_rate
        if aex_withdraw_limit is not None:
            config.aex_withdraw_limit = aex_withdraw_limit
        await self.session.flush()
        return config
