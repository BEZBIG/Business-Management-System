"""users table + user_role enum

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-14

Создаёт таблицу users с native PG enum user_role (user/manager/admin).
UUID PK использует uuid_generate_v4() из расширения uuid-ossp (уже создано в 0001).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт native enum user_role и таблицу users."""
    # 1. Создать native PG enum type с checkfirst — безопасно при повторном запуске
    user_role_enum = postgresql.ENUM(
        "user",
        "manager",
        "admin",
        name="user_role",
        create_type=False,
    )
    user_role_enum.create(op.get_bind(), checkfirst=True)

    # 2. Создать таблицу users
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(1024), nullable=False),
        # Используем postgresql.ENUM с create_type=False — тип создан отдельно выше
        # Это предотвращает дублирование CREATE TYPE внутри CREATE TABLE (КРИТИЧНО)
        sa.Column(
            "role",
            postgresql.ENUM("user", "manager", "admin", name="user_role", create_type=False),
            nullable=False,
            server_default="user",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 3. Уникальный индекс на email
    op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    """Удаляет индекс, таблицу и enum user_role."""
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
