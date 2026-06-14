"""Async-скрипт верификации схемы таблицы users через information_schema.columns.

Используется как verify-гейт миграции после alembic upgrade head.
Выходит с кодом 0 и выводит 'schema ok' при успехе,
либо выводит недостающие колонки в stderr и завершается с кодом 1.
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

REQUIRED_COLUMNS = {"id", "email", "password_hash", "role", "is_active", "created_at", "updated_at"}


async def _check() -> None:
    """Проверяет наличие всех обязательных колонок таблицы users через information_schema."""
    from app.core.config import settings  # noqa: PLC0415

    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'users' AND table_schema = 'public'"
                )
            )
            actual_columns = {row[0] for row in result.fetchall()}
    finally:
        await engine.dispose()

    missing = REQUIRED_COLUMNS - actual_columns
    if missing:
        print(f"SCHEMA ERROR: missing columns in 'users': {sorted(missing)}", file=sys.stderr)
        sys.exit(1)

    print("schema ok")


if __name__ == "__main__":
    asyncio.run(_check())
