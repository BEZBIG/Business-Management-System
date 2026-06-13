"""Тесты конфигурации фабрики сессий БД: expire_on_commit=False и lazy='raise' на связях."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import relationship


@pytest.mark.asyncio
async def test_session_factory_config() -> None:
    """async_sessionmaker должен иметь expire_on_commit=False."""
    from app.db.engine import async_session_factory  # noqa: PLC0415

    kw = async_session_factory.kw
    assert kw.get("expire_on_commit") is False, (
        "async_sessionmaker must be configured with expire_on_commit=False "
        "to prevent MissingGreenlet errors during async Pydantic serialization"
    )


def test_lazy_raise_on_access() -> None:
    """Обращение к связи без eager-load должно сразу бросать InvalidRequestError."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.db.base import Base, TimestampMixin  # noqa: PLC0415

    class Parent(Base, TimestampMixin):
        __tablename__ = "test_parent_lazy_raise"
        __table_args__ = {"extend_existing": True}
        id: int = Column(Integer, primary_key=True)
        name: str = Column(String(50))
        children = relationship("Child", lazy="raise", back_populates="parent")

    class Child(Base, TimestampMixin):
        __tablename__ = "test_child_lazy_raise"
        __table_args__ = {"extend_existing": True}
        id: int = Column(Integer, primary_key=True)
        parent_id: int = Column(Integer, ForeignKey("test_parent_lazy_raise.id"), nullable=False)
        parent = relationship("Parent", lazy="raise", back_populates="children")

    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as session:
        parent = Parent(id=1, name="test")
        session.add(parent)
        session.commit()

    with Session(engine) as session:
        loaded = session.get(Parent, 1)
        session.expunge(loaded)  # type: ignore[arg-type]

    with pytest.raises(InvalidRequestError):
        _ = loaded.children  # type: ignore[union-attr]
