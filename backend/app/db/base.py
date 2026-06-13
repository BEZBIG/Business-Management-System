"""Базовые ORM-классы SQLAlchemy: общий Base и миксин с метками времени."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Общий декларативный базовый класс для всех ORM-моделей."""


class TimestampMixin:
    """Добавляет колонки created_at и updated_at (timezone-aware) в ORM-модель."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
