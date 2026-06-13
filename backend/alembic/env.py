"""
Alembic migration environment — async pattern for SQLAlchemy + asyncpg.

Key design decisions (RESEARCH.md Pattern 4, Pitfall 3):
  - Uses create_async_engine() + connection.run_sync() — the ONLY correct async pattern.
  - Does NOT use async_engine_from_config() — this function does NOT exist in Alembic 1.18.4.
  - DSN comes from settings.database_url (env var), never hardcoded (D-06, T-02-01).
  - target_metadata = Base.metadata enables autogenerate for future domain models.
  - Offline mode uses a sync URL derived from the async DSN for plain SQL output.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# ---------------------------------------------------------------------------
# Alembic config object — access to alembic.ini values
# ---------------------------------------------------------------------------

config = context.config

# Configure Python logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Import ORM metadata and settings AFTER logging is configured
# ---------------------------------------------------------------------------

# Import Base so that all future model modules that import Base register
# their tables with Base.metadata (autogenerate support)
from app.core.config import settings  # noqa: E402
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Offline migration (plain SQL output, no DB connection required)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection.

    Outputs the SQL to stdout / a file.  Uses a sync-compatible URL
    (swap asyncpg driver for psycopg2 for offline mode).
    """
    # Convert async DSN to a sync-compatible one for offline SQL generation
    url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migration (async engine + run_sync)
# ---------------------------------------------------------------------------


def do_run_migrations(connection: Connection) -> None:
    """Configure Alembic context and run migrations against the given connection.

    Called by run_sync() inside the async engine's connection context.
    This is a synchronous function — run_sync() bridges the async/sync boundary.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # detect column type changes in autogenerate
        compare_server_default=True,  # detect server_default changes
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via run_sync().

    Pattern: create_async_engine + connection.run_sync() — VERIFIED working.
    NOT async_engine_from_config() — that function does NOT exist (Pitfall 3).
    """
    connectable = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,  # NullPool: no persistent pool during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — called by Alembic when DB is available."""
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Dispatch: offline vs online
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
