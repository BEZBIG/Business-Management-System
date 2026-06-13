"""
FastAPI dependency for yielding an async SQLAlchemy session.

Usage in a FastAPI endpoint:
    from fastapi import Depends
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.session import get_async_session

    @router.get("/items")
    async def list_items(session: AsyncSession = Depends(get_async_session)):
        ...

The dependency:
  1. Opens a session via async_session_factory (expire_on_commit=False — Pitfall 2).
  2. Yields the session to the endpoint handler.
  3. On success: commits the transaction.
  4. On exception: rolls back and re-raises.
  5. Session is always closed by the context manager after yield.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession per request.

    Commits on success, rolls back on any exception.
    Session lifetime is scoped to the HTTP request (or caller scope).
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
