"""ORM-модели Meeting, MeetingParticipant и перечисление MeetingStatus для домена встреч."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class MeetingStatus(enum.Enum):
    """Статусы встречи: активна или отменена."""

    ACTIVE = "active"
    CANCELLED = "cancelled"


class Meeting(Base, TimestampMixin):
    """ORM-модель встречи команды.

    Таблица meetings содержит время начала/конца (TIMESTAMPTZ),
    уникальный токен Jitsi-комнаты и статус (active/cancelled).
    Отмена выполняется через status=CANCELLED — без hard-delete.
    """

    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    end_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[MeetingStatus] = mapped_column(
        # values_callable: биндить .value (lowercase), а не имя члена enum
        Enum(
            MeetingStatus,
            name="meeting_status",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=MeetingStatus.ACTIVE,
        server_default="active",
    )
    jitsi_room_token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    # lazy="raise" — загружать явно через selectinload в service
    participants: Mapped[list[MeetingParticipant]] = relationship(
        back_populates="meeting",
        lazy="raise",
        cascade="all, delete-orphan",
    )


class MeetingParticipant(Base, TimestampMixin):
    """Ассоциативная таблица meeting_participants.

    Составной PK (meeting_id, user_id) — без surrogate UUID.
    Аналог TeamMember, но без колонки роли.
    """

    __tablename__ = "meeting_participants"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("meetings.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # lazy="raise" — загружать явно через selectinload в service
    meeting: Mapped[Meeting] = relationship(back_populates="participants", lazy="raise")
    user: Mapped[object] = relationship("User", lazy="raise")
