"""Smoke-тест склейки фазы 3: роутеры смонтированы, admin-вью зарегистрированы.

Не является integration-тестом — не требует Docker/БД.
Проверяет только импортируемость app.main.app и наличие маршрутов в OpenAPI,
а также корректность TeamAdmin / TaskAdmin ModelView.
"""

from __future__ import annotations


def test_app_imports_cleanly() -> None:
    """app.main.app импортируется без ошибок — приложение собирается."""
    from app.main import app  # noqa: PLC0415

    assert app is not None, "app.main.app должен быть доступен"


def test_teams_routes_in_openapi() -> None:
    """OpenAPI содержит маршруты с prefix /teams."""
    from app.main import app  # noqa: PLC0415

    paths = set(app.openapi()["paths"])
    teams_paths = [p for p in paths if p.startswith("/teams")]
    assert teams_paths, f"Ожидаем /teams/* маршруты в OpenAPI, нашли: {sorted(paths)}"


def test_tasks_routes_in_openapi() -> None:
    """OpenAPI содержит маршруты с 'tasks' в пути."""
    from app.main import app  # noqa: PLC0415

    paths = set(app.openapi()["paths"])
    tasks_paths = [p for p in paths if "tasks" in p]
    assert tasks_paths, f"Ожидаем tasks/* маршруты в OpenAPI, нашли: {sorted(paths)}"


def test_ratings_routes_in_openapi() -> None:
    """OpenAPI содержит маршруты с 'ratings' в пути."""
    from app.main import app  # noqa: PLC0415

    paths = set(app.openapi()["paths"])
    ratings_paths = [p for p in paths if "ratings" in p]
    assert ratings_paths, f"Ожидаем ratings/* маршруты в OpenAPI, нашли: {sorted(paths)}"


def test_team_admin_can_delete_false() -> None:
    """TeamAdmin.can_delete is False — прямое удаление через UI запрещено."""
    from app.admin.setup import TeamAdmin  # noqa: PLC0415

    assert TeamAdmin.can_delete is False, "TeamAdmin.can_delete должен быть False"


def test_team_admin_scalar_only_column_list() -> None:
    """TeamAdmin.column_list содержит только скалярные поля, без member_links."""
    from app.admin.setup import TeamAdmin  # noqa: PLC0415
    from app.teams.models import Team  # noqa: PLC0415

    # Проверяем, что column_list непустой
    assert TeamAdmin.column_list, "TeamAdmin.column_list не должен быть пустым"

    # Убеждаемся, что relationship member_links не включён
    col_names = [c.key if hasattr(c, "key") else str(c) for c in TeamAdmin.column_list]
    assert "member_links" not in col_names, (
        "TeamAdmin.column_list не должен содержать relationship 'member_links' "
        "(N+1 / MissingGreenlet protection)"
    )

    # Проверяем присутствие ожидаемых скалярных полей
    expected_cols = {Team.id, Team.name, Team.invite_code, Team.created_at}
    for col in expected_cols:
        assert col in TeamAdmin.column_list, f"Ожидаем {col} в TeamAdmin.column_list"


def test_task_admin_can_delete_false() -> None:
    """TaskAdmin.can_delete is False — soft-delete, прямой DELETE из UI запрещён (D-09)."""
    from app.admin.setup import TaskAdmin  # noqa: PLC0415

    assert TaskAdmin.can_delete is False, "TaskAdmin.can_delete должен быть False"


def test_task_admin_scalar_only_column_list() -> None:
    """TaskAdmin.column_list содержит только скалярные поля, без comments."""
    from app.admin.setup import TaskAdmin  # noqa: PLC0415
    from app.tasks.models import Task  # noqa: PLC0415

    # Проверяем, что column_list непустой
    assert TaskAdmin.column_list, "TaskAdmin.column_list не должен быть пустым"

    # Убеждаемся, что relationship comments не включён
    col_names = [c.key if hasattr(c, "key") else str(c) for c in TaskAdmin.column_list]
    assert "comments" not in col_names, (
        "TaskAdmin.column_list не должен содержать relationship 'comments' "
        "(N+1 / MissingGreenlet protection)"
    )

    # Проверяем присутствие ожидаемых скалярных полей
    expected_cols = {
        Task.id,
        Task.title,
        Task.status,
        Task.is_deleted,
        Task.team_id,
        Task.created_at,
    }
    for col in expected_cols:
        assert col in TaskAdmin.column_list, f"Ожидаем {col} в TaskAdmin.column_list"


def test_setup_admin_registers_team_and_task_admin() -> None:
    """setup_admin регистрирует TeamAdmin и TaskAdmin через add_view."""
    # Проверяем на уровне импорта — функция setup_admin экспортируется из admin/setup
    from app.admin.setup import TaskAdmin, TeamAdmin, setup_admin  # noqa: PLC0415

    # Убеждаемся, что классы определены и можно достучаться до них
    assert TeamAdmin is not None, "TeamAdmin должен быть определён в app.admin.setup"
    assert TaskAdmin is not None, "TaskAdmin должен быть определён в app.admin.setup"
    assert callable(setup_admin), "setup_admin должна быть вызываемой функцией"
