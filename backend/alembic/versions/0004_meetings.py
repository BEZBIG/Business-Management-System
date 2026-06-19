"""meetings, meeting_participants tables + meeting_status enum

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-19

Создаёт native PG enum meeting_status и две таблицы фазы 4.
Порядок: enum создаётся ДО create_table (Pitfall 2 — DuplicateObject).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт enum meeting_status и таблицы meetings, meeting_participants."""
    # 1. Создать native PG enum meeting_status (ОБЯЗАТЕЛЬНО перед create_table — Pitfall 2)
    meeting_status_enum = postgresql.ENUM(
        "active",
        "cancelled",
        name="meeting_status",
        create_type=False,
    )
    meeting_status_enum.create(op.get_bind(), checkfirst=True)

    # 2. Таблица meetings (D-01: team_id NOT NULL; D-09: jitsi_room_token unique; D-12: status)
    op.create_table(
        "meetings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "creator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "start_time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "end_time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("active", "cancelled", name="meeting_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "jitsi_room_token",
            sa.String(64),
            nullable=False,
        ),
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
    # Индекс по team_id для фильтрации встреч команды
    op.create_index("ix_meetings_team_id", "meetings", ["team_id"])
    # Составной индекс (status, start_time) для conflict-check и calendar-запросов (T-04-02)
    op.create_index("ix_meetings_status_start", "meetings", ["status", "start_time"])
    # Уникальный индекс для jitsi_room_token (D-09)
    op.create_index("ix_meetings_jitsi_token", "meetings", ["jitsi_room_token"], unique=True)

    # 3. Ассоциативная таблица meeting_participants (D-02: составной PK)
    op.create_table(
        "meeting_participants",
        sa.Column(
            "meeting_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("meetings.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
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
    # Индекс по user_id для поиска встреч пользователя (conflict-check)
    op.create_index("ix_mp_user_id", "meeting_participants", ["user_id"])
    # Индекс по meeting_id для быстрого получения участников встречи
    op.create_index("ix_mp_meeting_id", "meeting_participants", ["meeting_id"])


def downgrade() -> None:
    """Удаляет таблицы и enum в обратном порядке FK-зависимостей."""
    op.drop_index("ix_mp_meeting_id", table_name="meeting_participants")
    op.drop_index("ix_mp_user_id", table_name="meeting_participants")
    op.drop_table("meeting_participants")

    op.drop_index("ix_meetings_jitsi_token", table_name="meetings")
    op.drop_index("ix_meetings_status_start", table_name="meetings")
    op.drop_index("ix_meetings_team_id", table_name="meetings")
    op.drop_table("meetings")

    op.execute("DROP TYPE IF EXISTS meeting_status")
