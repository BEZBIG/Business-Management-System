"""
DB session factory configuration tests — NFR-01 criterion #4.

Tests:
  test_session_factory_config — async_sessionmaker must have expire_on_commit=False
  test_lazy_raise_on_access   — ORM relationships must use lazy="raise"

Activated in plan 01-02 (Wave 2): skip decorators removed; implementation added.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Column, DateTime, Integer, String, func
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import relationship


@pytest.mark.asyncio
async def test_session_factory_config() -> None:
    """The async_sessionmaker must be configured with expire_on_commit=False.

    NFR-01 criterion #4 — prevents MissingGreenlet after commit during
    Pydantic serialization (see RESEARCH.md Pitfall 2).
    """
    from app.db.engine import async_session_factory  # noqa: PLC0415

    kw = async_session_factory.kw
    assert kw.get("expire_on_commit") is False, (
        "async_sessionmaker must be configured with expire_on_commit=False "
        "to prevent MissingGreenlet errors during async Pydantic serialization "
        "(NFR-01 criterion #4, RESEARCH.md Pitfall 2)"
    )


def test_lazy_raise_on_access() -> None:
    """Accessing an ORM relationship without eager-loading must raise immediately.

    NFR-01 criterion #4 (secure behaviour) — lazy='raise' forces explicit
    selectinload()/joinedload(), blocking accidental sync DB access in async context.

    This test builds minimal local ORM models on TimestampMixin/Base to prove
    the lazy='raise' pattern raises InvalidRequestError immediately.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base, TimestampMixin  # noqa: PLC0415

    # ---- Build test-local models --------------------------------------------
    class Parent(Base, TimestampMixin):
        __tablename__ = "test_parent_lazy_raise"
        id: int = Column(Integer, primary_key=True)
        name: str = Column(String(50))
        # lazy="raise" — accessing this without eager-load must raise immediately
        children = relationship("Child", lazy="raise", back_populates="parent")

    class Child(Base, TimestampMixin):
        __tablename__ = "test_child_lazy_raise"
        id: int = Column(Integer, primary_key=True)
        parent_id: int = Column(Integer)
        parent = relationship("Parent", lazy="raise", back_populates="children")

    # ---- Spin up an in-memory SQLite engine for the test --------------------
    # We only need to prove lazy="raise" raises — no async required here
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        parent = Parent(id=1, name="test")
        session.add(parent)
        session.commit()

    # ---- Attempt lazy access on a detached instance -------------------------
    # Load a fresh instance (no eager load of children)
    with Session(engine) as session:
        loaded = session.get(Parent, 1)
        session.expunge(loaded)  # detach so lazy access definitely hits the guard

    # Accessing the relationship on a detached object must raise immediately
    with pytest.raises(InvalidRequestError):
        _ = loaded.children  # type: ignore[union-attr]
