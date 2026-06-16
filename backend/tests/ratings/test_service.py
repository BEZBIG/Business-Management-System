"""Stub-тесты сервисного слоя оценок (Wave 0 — RED).

Тесты завершаются pytest.skip при отсутствии модуля app.ratings,
и pytest.fail когда модуль уже есть, но тест-тело не написано.
"""

from __future__ import annotations

import pytest


def test_rating_guards() -> None:
    """RATE-01: Rating при status!=done → 422; rater==ratee → 403."""
    try:
        import app.ratings  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.ratings not yet implemented")
    pytest.fail("test_rating_guards not implemented")


def test_rating_upsert() -> None:
    """RATE-01: повторный rating → upsert (score обновляется)."""
    try:
        import app.ratings  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.ratings not yet implemented")
    pytest.fail("test_rating_upsert not implemented")


def test_avg_alltime() -> None:
    """RATE-02: AVG alltime = математически верное значение."""
    try:
        import app.ratings  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.ratings not yet implemented")
    pytest.fail("test_avg_alltime not implemented")


def test_avg_period() -> None:
    """RATE-03: AVG за период фильтрует по created_at."""
    try:
        import app.ratings  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.ratings not yet implemented")
    pytest.fail("test_avg_period not implemented")
