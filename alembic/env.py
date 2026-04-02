"""Alembic environment."""

from __future__ import annotations

import importlib
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.core.config import settings
from app.models.base import Base


def load_models() -> None:
    for module_name in (
        "app.models.admin",
        "app.models.city",
        "app.models.config",
        "app.models.order",
        "app.models.rate",
        "app.models.user",
    ):
        importlib.import_module(module_name)


load_models()

config_obj = context.config
config_obj.set_main_option("sqlalchemy.url", settings.database_url)

if config_obj.config_file_name is not None:
    fileConfig(config_obj.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config_obj.get_section(config_obj.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
