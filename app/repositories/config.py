"""Репозиторий конфигурации."""

from __future__ import annotations

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

    async def set_allowance(self, value: float) -> Config:
        config = await self.get_or_create()
        config.allowance = value
        await self.session.flush()
        return config
