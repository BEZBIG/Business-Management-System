"""Stub-тесты сервисного слоя задач (Wave 0 — RED).

Тесты завершаются pytest.skip при отсутствии модуля app.tasks,
и pytest.fail когда модуль уже есть, но тест-тело не написано.
"""

from __future__ import annotations

import pytest


def test_task_crud() -> None:
    """TASK-01: CRUD задач; soft-delete: задача не видна в списке после удаления."""
    try:
        import app.tasks  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.tasks not yet implemented")
    pytest.fail("test_task_crud not implemented")


def test_assignee_membership() -> None:
    """TASK-02: assignee должен быть членом команды; нечлен → 422."""
    try:
        import app.tasks  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.tasks not yet implemented")
    pytest.fail("test_assignee_membership not implemented")


def test_deadline_tz() -> None:
    """TASK-03: deadline сохраняется timezone-aware; None допустим."""
    try:
        import app.tasks  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.tasks not yet implemented")
    pytest.fail("test_deadline_tz not implemented")


def test_status_transitions() -> None:
    """TASK-04: open→done = 422; open→in_progress = ok; done→in_progress = ok."""
    try:
        import app.tasks  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.tasks not yet implemented")
    pytest.fail("test_status_transitions not implemented")
