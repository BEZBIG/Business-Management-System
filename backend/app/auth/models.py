"""ORM-модель User и перечисление UserRole для домена аутентификации."""

from __future__ import annotations

import enum
import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class UserRole(enum.Enum):
    """Роли пользователей системы."""

    USER = "user"
    MANAGER = "manager"
    ADMIN = "admin"


class User(Base, TimestampMixin):
    """ORM-модель пользователя. Таблица users в PostgreSQL."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("uuid_generate_v4()"),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    password_hash: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        # values_callable: биндить .value (lowercase 'user'/'manager'/'admin'), а не
        # имя члена enum ('USER') — иначе INSERT падает на native PG enum user_role,
        # значения которого создаются миграцией в нижнем регистре.
        Enum(
            UserRole,
            name="user_role",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=UserRole.USER,
        server_default="user",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean(),
        nullable=False,
        default=True,
        server_default="true",
    )
    # created_at и updated_at наследуются от TimestampMixin — не дублировать
