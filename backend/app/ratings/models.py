"""ORM-модель Rating для домена оценок."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Rating(Base, TimestampMixin):
    """ORM-модель оценки выполненной задачи (D-12, D-14).

    UNIQUE(task_id, rater_id) — блокирует дублирование оценок на уровне БД.
    rater_id и ratee_id nullable с SET NULL — защита истории при удалении пользователя.
    """

    __tablename__ = "ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tasks.id"),
        nullable=False,
    )
    rater_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ratee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    score: Mapped[int] = mapped_column(
        sa.SmallInteger(),
        nullable=False,
    )

    __table_args__ = (
        sa.UniqueConstraint("task_id", "rater_id", name="uq_ratings_task_rater"),
    )
