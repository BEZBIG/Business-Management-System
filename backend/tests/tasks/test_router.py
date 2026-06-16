"""Stub-тесты HTTP-роутера задач (Wave 0 — RED, интеграционные).

Маркер pytest.mark.integration обязателен — тесты требуют реальной БД.
Тесты завершаются pytest.skip при отсутствии модуля app.tasks.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_task_crud() -> None:
    """TASK-01: CRUD задач + soft-delete через HTTP-эндпоинты."""
    try:
        import app.tasks  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.tasks not yet implemented")
    pytest.fail("test_task_crud not implemented")


@pytest.mark.integration
def test_task_detail_comments() -> None:
    """TASK-05: GET /tasks/{id} содержит вложенный массив comments."""
    try:
        import app.tasks  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.tasks not yet implemented")
    pytest.fail("test_task_detail_comments not implemented")
