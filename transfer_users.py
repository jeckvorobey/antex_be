"""Скрипт миграции пользователей из SQLite → PostgreSQL."""

from __future__ import annotations

import asyncio
import sqlite3
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.database import async_session
from app.enums.user import UserRole
from app.models.user import User


async def transfer(sqlite_path: str) -> None:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT id, username, first_name, last_name, language_code, is_bot, is_premium FROM users"
    )
    rows = cursor.fetchall()
    conn.close()

    transferred = 0
    skipped = 0

    async with async_session() as session, session.begin():
        for row in rows:
            telegram_id = row["id"]
            exists = await session.execute(select(User.id).where(User.telegram_id == telegram_id))
            if exists.scalar_one_or_none() is not None:
                skipped += 1
                continue

            user = User(
                telegram_id=telegram_id,
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                language_code=row["language_code"],
                language_code_app=row["language_code"] or "ru",
                is_bot=bool(row["is_bot"]),
                is_premium=bool(row["is_premium"]),
                role=int(UserRole.USER),
            )
            session.add(user)
            transferred += 1

    print(f"Готово. Перенесено: {transferred}, пропущено (дубли): {skipped}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Использование: python transfer_users.py /path/to/db.sqlite")
        sys.exit(1)
    asyncio.run(transfer(sys.argv[1]))
