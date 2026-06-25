"""Тест регистрации ORM-моделей фазы 3 в Base.metadata (НЕ интеграционный).

RED до выполнения Task 2 (модели ещё не созданы → pytest.skip).
GREEN после Task 2 (пять таблиц + UniqueConstraint в metadata).
"""

from __future__ import annotations

import pytest


def test_phase3_tables_in_metadata() -> None:
    """Пять таблиц фазы 3 присутствуют в Base.metadata после импорта моделей."""
    try:
        from app.ratings.models import Rating  # noqa: F401
        from app.tasks.models import Task, TaskComment  # noqa: F401
        from app.teams.models import Team, TeamMember  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("Phase 3 models not yet implemented")

    from app.db.base import Base

    tables = Base.metadata.tables
    expected = {"teams", "team_members", "tasks", "task_comments", "ratings"}
    missing = expected - set(tables.keys())
    assert not missing, f"Таблицы не найдены в Base.metadata: {missing}"


def test_ratings_unique_constraint() -> None:
    """UniqueConstraint uq_ratings_task_rater присутствует на таблице ratings."""
    try:
        from app.ratings.models import Rating  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.ratings not yet implemented")

    from sqlalchemy import UniqueConstraint

    from app.db.base import Base

    ratings_table = Base.metadata.tables.get("ratings")
    assert ratings_table is not None, "Таблица ratings не найдена в metadata"

    constraint_names = {
        c.name for c in ratings_table.constraints if isinstance(c, UniqueConstraint)
    }
    assert "uq_ratings_task_rater" in constraint_names, (
        f"UniqueConstraint uq_ratings_task_rater не найден. Есть: {constraint_names}"
    )


def test_team_member_composite_pk() -> None:
    """TeamMember имеет составной PK (team_id, user_id), не surrogate UUID."""
    try:
        from app.teams.models import TeamMember  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.teams not yet implemented")

    from app.db.base import Base

    table = Base.metadata.tables.get("team_members")
    assert table is not None, "Таблица team_members не найдена"

    pk_cols = [col.name for col in table.primary_key.columns]
    assert set(pk_cols) == {"team_id", "user_id"}, (
        f"Ожидался составной PK (team_id, user_id), получен: {pk_cols}"
    )
