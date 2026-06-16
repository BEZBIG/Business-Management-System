"""Stub-тесты HTTP-роутера команд (Wave 0 — RED, интеграционные).

Маркер pytest.mark.integration обязателен — тесты требуют реальной БД.
Тесты завершаются pytest.skip при отсутствии модуля app.teams.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
def test_join_team() -> None:
    """TEAM-02: POST /teams/{id}/join с верным кодом → 200; неверный → 400."""
    try:
        import app.teams  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.teams not yet implemented")
    pytest.fail("test_join_team not implemented")


@pytest.mark.integration
def test_remove_member_rbac() -> None:
    """TEAM-03: remove_member: owner/manager → 200; member → 403."""
    try:
        import app.teams  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.teams not yet implemented")
    pytest.fail("test_remove_member_rbac not implemented")


@pytest.mark.integration
def test_assign_role_rbac() -> None:
    """TEAM-04: назначение роли: owner → 200; member → 403."""
    try:
        import app.teams  # noqa: F401
    except ModuleNotFoundError:
        pytest.skip("app.teams not yet implemented")
    pytest.fail("test_assign_role_rbac not implemented")
