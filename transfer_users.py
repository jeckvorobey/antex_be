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


def read_old_users(db_path: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT id, username, first_name, last_name, language_code, is_bot, is_premium FROM users"
    )
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


async def transfer() -> None:
    db_path = input("Путь к старой SQLite базе: ").strip()
    old_users = read_old_users(db_path)
    print(f"Найдено {len(old_users)} пользователей в старой БД")

    added = 0
    skipped = 0

    async with async_session() as session, session.begin():
        for row in old_users:
            tg_id = row["id"]
            exists = await session.execute(select(User.id).where(User.telegram_id == tg_id))
            if exists.scalar_one_or_none() is not None:
                skipped += 1
                continue

            lang = (row["language_code"] or "")[:10]
            user = User(
                telegram_id=tg_id,
                username=row["username"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                language_code=lang or None,
                language_code_app=lang or "ru",
                is_bot=bool(row["is_bot"]),
                is_premium=bool(row["is_premium"]),
                role=int(UserRole.USER),
            )
            session.add(user)
            added += 1

    print(f"Перенесено: {added}, пропущено: {skipped}")


if __name__ == "__main__":
    asyncio.run(transfer())
