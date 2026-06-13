"""baseline

Revision ID: 0001
Revises:
Create Date: 2026-06-13

Базовая миграция: создаёт расширение uuid-ossp, доменных таблиц пока нет.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт расширение uuid-ossp."""
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')


def downgrade() -> None:
    """Удаляет расширение uuid-ossp."""
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
