"""
Async SQLAlchemy engine and session factory for TeamFlow.

Exports:
  engine                — AsyncEngine backed by asyncpg (postgresql+asyncpg DSN).
  async_session_factory — async_sessionmaker with expire_on_commit=False (NFR-01 #4).

Key design choices:
  - expire_on_commit=False: prevents MissingGreenlet after commit during Pydantic
    serialization (RESEARCH.md Pitfall 2, NFR-01 criterion #4).
  - pool_pre_ping=True: validates connection health before yielding from pool;
    prevents stale-connection errors after DB restart (T-02-02).
  - pool_size / max_overflow: conservative defaults from Settings (D-13);
    tunable via env vars; real tuning for 10k users deferred to Phase 7.
  - echo=True only in dev environment (settings.environment == "dev").
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# ---------------------------------------------------------------------------
# Async engine — uses asyncpg driver (postgresql+asyncpg:// DSN from Settings)
# ---------------------------------------------------------------------------

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,  # default 10, D-13
    max_overflow=settings.db_max_overflow,  # default 5, D-13
    pool_pre_ping=True,  # health-check before yielding from pool, T-02-02
    echo=settings.environment == "dev",  # SQL logging in dev only
)

# ---------------------------------------------------------------------------
# Session factory — expire_on_commit=False is MANDATORY for async (NFR-01 #4)
# ---------------------------------------------------------------------------

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # prevents MissingGreenlet after commit (Pitfall 2)
    autoflush=False,  # explicit flush; avoids implicit I/O surprises
)
