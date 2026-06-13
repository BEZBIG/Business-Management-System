"""
SQLAlchemy ORM base classes for TeamFlow.

Provides:
  Base         — DeclarativeBase; all ORM models inherit from this.
  TimestampMixin — created_at / updated_at columns using DateTime(timezone=True)
                   (maps to TIMESTAMPTZ in PostgreSQL — NFR-01 criterion #3, D-10).

Convention: ALL relationships in every model MUST declare lazy="raise" so that
accidental lazy-load in an async context is caught immediately in development
(NFR-01 criterion #4). Use selectinload() / joinedload() explicitly.

Example:
    class User(Base, TimestampMixin):
        __tablename__ = "users"
        id: Mapped[int] = mapped_column(Integer, primary_key=True)
        tasks: Mapped[list["Task"]] = relationship("Task", lazy="raise", back_populates="owner")
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    All models inherit from Base (and optionally TimestampMixin).
    Do NOT add table-level columns here — keep Base minimal so that
    test-local temporary models can cleanly subclass it.
    """


class TimestampMixin:
    """Adds created_at / updated_at columns to any ORM model.

    Both columns use DateTime(timezone=True) which maps to TIMESTAMPTZ in
    PostgreSQL via asyncpg.  This ensures all timestamp comparisons are
    timezone-aware and prevents the naive/aware datetime mismatch error
    (RESEARCH.md Pitfall 6, D-10, NFR-01 criterion #3).

    server_default=func.now() — DB sets the value on INSERT.
    onupdate=func.now()       — DB sets the value on UPDATE.

    Usage:
        class MyModel(Base, TimestampMixin):
            __tablename__ = "my_model"
            ...
    """

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
