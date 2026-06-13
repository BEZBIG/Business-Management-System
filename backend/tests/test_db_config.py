"""
DB session factory configuration tests — NFR-01 criterion #4.

Tests:
  test_session_factory_config — async_sessionmaker must have expire_on_commit=False
  test_lazy_raise_on_access   — ORM relationships must use lazy="raise"

These are Wave 0 stubs: the session factory and ORM models are implemented in
plan 01-02.  Until then both tests are SKIPPED with a clear reason.

When 01-02 is complete:
  1. Remove the pytest.mark.skip decorators.
  2. Ensure `app.db.engine` exports `async_session_factory`.
  3. Ensure `app.db.base` exports a model with a relationship configured lazy="raise".
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="app.db.engine.async_session_factory implemented in plan 01-02")
@pytest.mark.asyncio
async def test_session_factory_config() -> None:
    """The async_sessionmaker must be configured with expire_on_commit=False.

    NFR-01 criterion #4 — prevents MissingGreenlet after commit during
    Pydantic serialization (see RESEARCH.md Pitfall 2).

    How to verify after 01-02:
      from app.db.engine import async_session_factory
      assert async_session_factory.kw.get("expire_on_commit") is False
    """
    from app.db.engine import async_session_factory  # noqa: PLC0415

    kw = async_session_factory.kw
    assert kw.get("expire_on_commit") is False, (
        "async_sessionmaker must be configured with expire_on_commit=False "
        "to prevent MissingGreenlet errors during async Pydantic serialization "
        "(NFR-01 criterion #4, RESEARCH.md Pitfall 2)"
    )


@pytest.mark.skip(reason="ORM relationships with lazy='raise' implemented in plan 01-02+")
@pytest.mark.asyncio
async def test_lazy_raise_on_access() -> None:
    """Accessing an ORM relationship without eager-loading must raise immediately.

    NFR-01 criterion #4 (secure behaviour) — lazy="raise" forces explicit
    selectinload()/joinedload(), blocking accidental sync DB access in async context.

    Phase 1 has no domain models with relationships yet.
    This test is enabled when the first model with a relationship is added (Phase 2+).

    How to verify after Phase 2:
      from sqlalchemy.orm import Session
      from sqlalchemy.exc import InvalidRequestError
      from app.db.base import Base

      # Build a detached instance and attempt lazy access
      instance = SomeModel()  # model with lazy="raise" relationship
      with pytest.raises(InvalidRequestError):
          _ = instance.some_relationship  # must raise, not block
    """
    # Placeholder assertion — the real check is documented above
    pytest.fail(
        "test_lazy_raise_on_access: implement when first ORM relationship is added (Phase 2+). "
        "Verify that accessing a relationship on a detached instance raises "
        "sqlalchemy.exc.InvalidRequestError immediately."
    )
