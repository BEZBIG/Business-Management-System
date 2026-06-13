"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-06-13

Purpose (D-09): Baseline migration — proves async Alembic pipeline works end-to-end.
  Contains only the uuid-ossp PostgreSQL extension (no domain tables yet).
  Domain tables (users, teams, tasks, ...) will be added in Phase 2+.

Security note (T-02-03): Risk is low — no data or domain schema changed here.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the uuid-ossp extension (D-09).

    This is a baseline migration — no domain tables.
    Goal: prove that async Alembic pipeline (create_async_engine + run_sync)
    works end-to-end before any domain models are built (NFR-01 criterion #3).
    """
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')


def downgrade() -> None:
    """Drop the uuid-ossp extension."""
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
