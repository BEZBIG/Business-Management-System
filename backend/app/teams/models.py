"""ORM-модели Team, TeamMember и перечисление TeamRole для домена команд."""

from __future__ import annotations

import enum
import uuid

import sqlalchemy as sa
from sqlalchemy import Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class TeamRole(enum.Enum):
    """Роли участников команды."""

    OWNER = "owner"
    MANAGER = "manager"
    MEMBER = "member"


class TeamMember(Base, TimestampMixin):
    """Ассоциативная таблица team_members с ролью участника (D-01, D-02).

    Составной PK (team_id, user_id) — не surrogate UUID.
    """

    __tablename__ = "team_members"

    team_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("teams.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[TeamRole] = mapped_column(
        # values_callable: биндить .value (lowercase), а не имя члена enum
        Enum(
            TeamRole,
            name="team_role",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TeamRole.MEMBER,
        server_default="member",
    )

    # lazy="raise" — загружать явно через selectinload (зафиксировано в STATE)
    team: Mapped[Team] = relationship(back_populates="member_links", lazy="raise")
    user: Mapped[object] = relationship("User", lazy="raise")


class Team(Base, TimestampMixin):
    """ORM-модель команды. Таблица teams в PostgreSQL."""

    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    invite_code: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # Association object links — загружать через selectinload в service
    member_links: Mapped[list[TeamMember]] = relationship(
        back_populates="team",
        lazy="raise",
        cascade="all, delete-orphan",
    )
