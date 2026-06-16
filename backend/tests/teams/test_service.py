"""Stub-тесты сервисного слоя команд (Wave 0 — RED).

Тесты завершаются pytest.skip при отсутствии модуля app.teams,
и pytest.fail когда модуль уже есть, но тест-тело не написано.
"""

from __future__ import annotations

import pytest


def test_create_team() -> None:
    """TEAM-01: create_team генерирует invite_code и сохраняет команду."""
    try:
        import app.teams  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.teams not yet implemented")
    pytest.fail("test_create_team not implemented")


def test_join_team() -> None:
    """TEAM-02: join_team с верным кодом добавляет участника; неверный → ошибка."""
    try:
        import app.teams  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.teams not yet implemented")
    pytest.fail("test_join_team not implemented")


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
