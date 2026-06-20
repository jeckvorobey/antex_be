"""Alembic environment."""

from __future__ import annotations

import asyncio
import importlib
from logging.config import fileConfig

from alembic.config import Config
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.models.base import Base


def load_models() -> None:
    """Загружает единый экспорт моделей, чтобы Alembic видел всю metadata."""
    importlib.import_module("app.models")


load_models()
target_metadata = Base.metadata


def get_alembic_config() -> Config:
    """Возвращает активный Alembic config и подставляет URL из настроек."""
    config_obj = context.config
    config_obj.set_main_option("sqlalchemy.url", settings.database_url)

    if config_obj.config_file_name is not None:
        fileConfig(config_obj.config_file_name)

    return config_obj


def run_migrations_offline() -> None:
    """Генерирует SQL миграций без подключения к базе."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Запускает миграции внутри синхронного callback SQLAlchemy."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online(config_obj: Config) -> None:
    """Подключается к БД async engine и применяет миграции."""
    connectable = async_engine_from_config(
        config_obj.get_section(config_obj.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def is_alembic_runtime() -> bool:
    """Отличает запуск Alembic от тестового импорта env.py как модуля."""
    return hasattr(context, "config")


def run_migrations() -> None:
    """Точка входа env.py при запуске Alembic."""
    config_obj = get_alembic_config()

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        asyncio.run(run_migrations_online(config_obj))


if is_alembic_runtime():
    run_migrations()
