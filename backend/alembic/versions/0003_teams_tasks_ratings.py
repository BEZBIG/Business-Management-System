"""teams, team_members, tasks, task_comments, ratings tables + enums

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-16

Создаёт пять таблиц фазы 3 и два native PG enum: team_role, task_status.
Порядок: enum-типы создаются ДО create_table (Pitfall 2 — DuplicateObject).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Создаёт enum-типы и пять таблиц фазы 3."""
    # 1. Создать native PG enum team_role (ОБЯЗАТЕЛЬНО перед create_table — Pitfall 2)
    team_role_enum = postgresql.ENUM(
        "owner",
        "manager",
        "member",
        name="team_role",
        create_type=False,
    )
    team_role_enum.create(op.get_bind(), checkfirst=True)

    # 2. Создать native PG enum task_status
    task_status_enum = postgresql.ENUM(
        "open",
        "in_progress",
        "done",
        name="task_status",
        create_type=False,
    )
    task_status_enum.create(op.get_bind(), checkfirst=True)

    # 3. Таблица teams (FK-источник для team_members и tasks)
    op.create_table(
        "teams",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("invite_code", sa.String(64), nullable=False),
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
    op.create_index("ix_teams_invite_code", "teams", ["invite_code"], unique=True)

    # 4. Таблица team_members (ассоциативная, составной PK team_id+user_id — D-02)
    op.create_table(
        "team_members",
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
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
            "role",
            postgresql.ENUM("owner", "manager", "member", name="team_role", create_type=False),
            nullable=False,
            server_default="member",
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
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])

    # 5. Таблица tasks (D-05: team_id NOT NULL; D-06: task_status; D-09: soft-delete; D-10)
    op.create_table(
        "tasks",
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
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("open", "in_progress", "done", name="task_status", create_type=False),
            nullable=False,
            server_default="open",
        ),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
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
    # Составной индекс team_id+status для эффективной фильтрации задач по команде
    op.create_index("ix_tasks_team_id_status", "tasks", ["team_id", "status"])

    # 6. Таблица task_comments (D-11: append-only, автор может удалить своё)
    op.create_table(
        "task_comments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("body", sa.Text, nullable=False),
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

    # 7. Таблица ratings (D-12: ratee_id=assignee; D-14: UNIQUE task_id+rater_id)
    op.create_table(
        "ratings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tasks.id"),
            nullable=False,
        ),
        sa.Column(
            "rater_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ratee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("score", sa.SmallInteger(), nullable=False),
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
        sa.UniqueConstraint("task_id", "rater_id", name="uq_ratings_task_rater"),
    )
    # Индекс для AVG-запросов по исполнителю за период (RATE-02, RATE-03)
    op.create_index("ix_ratings_ratee_created", "ratings", ["ratee_id", "created_at"])


def downgrade() -> None:
    """Удаляет таблицы и enum-типы в обратном порядке FK-зависимостей."""
    op.drop_index("ix_ratings_ratee_created", table_name="ratings")
    op.drop_table("ratings")
    op.drop_table("task_comments")
    op.drop_index("ix_tasks_team_id_status", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_team_members_team_id", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_teams_invite_code", table_name="teams")
    op.drop_table("teams")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.execute("DROP TYPE IF EXISTS team_role")
