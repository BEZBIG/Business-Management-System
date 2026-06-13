"""FastAPI-зависимость, выдающая async-сессию SQLAlchemy.

Открывает сессию на запрос, коммитит при успехе и откатывает при исключении.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Зависимость FastAPI: выдаёт AsyncSession на запрос.

    Коммит при успехе, rollback при любом исключении; сессия закрывается контекст-менеджером.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
