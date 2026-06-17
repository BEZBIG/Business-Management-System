"""Тесты HTTP-роутера задач.

Unit-тесты RBAC используют DI-override и моки AsyncSession.
Интеграционные тесты помечены @pytest.mark.integration (требуют Docker-инфраструктуры).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

try:
    from app.auth.dependencies import get_current_user
    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token
    from app.db.session import get_async_session
    from app.main import app
    from app.tasks.dependencies import get_task_or_404, require_task_editor
    from app.tasks.models import Task, TaskStatus
    from app.teams.dependencies import get_team_membership
    from app.teams.models import TeamMember, TeamRole

    _TASKS_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _TASKS_AVAILABLE = False


def _make_user(role: UserRole | None = None, user_id: uuid.UUID | None = None) -> User:
    """Создаёт User без сохранения в БД."""
    if role is None:
        role = UserRole.USER
    u = User(email="t@example.com", password_hash="h", role=role, is_active=True)
    u.id = user_id or uuid.uuid4()
    return u


def _make_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    role: TeamRole | None = None,
) -> TeamMember:
    """Создаёт TeamMember без сохранения в БД."""
    if role is None:
        role = TeamRole.MEMBER
    m = TeamMember(team_id=team_id, user_id=user_id, role=role)
    m.created_at = datetime.now(UTC)
    return m


def _make_task(
    task_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
    status: TaskStatus = TaskStatus.OPEN,
) -> Task:
    """Создаёт Task без сохранения в БД."""
    t = Task(
        team_id=team_id or uuid.uuid4(),
        creator_id=creator_id or uuid.uuid4(),
        title="Test task",
        status=status,
    )
    t.id = task_id or uuid.uuid4()
    t.is_deleted = False
    t.assignee_id = None
    t.description = None
    t.deadline = None
    t.archived_at = None
    t.comments = []
    t.created_at = datetime.now(UTC)
    return t


# ---------------------------------------------------------------------------
# Unit-тесты (без живой БД — DI-override)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_task_unit() -> None:
    """POST /teams/{id}/tasks создаёт задачу и возвращает 201 + TaskResponse."""
    if not _TASKS_AVAILABLE:
        pytest.skip("app.tasks not yet implemented")

    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    member = _make_member(team_id, user_id, TeamRole.MEMBER)
    task = _make_task(team_id=team_id, creator_id=user_id)

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.tasks.router.create_task", return_value=task),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_team_membership] = lambda: member

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.post(
                    f"/teams/{team_id}/tasks", json={"title": "Test task"}
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Test task"
    assert body["status"] == "open"


@pytest.mark.asyncio
async def test_list_tasks_non_member_404() -> None:
    """GET /teams/{id}/tasks: не-член получает 404 (анти-энумерация)."""
    if not _TASKS_AVAILABLE:
        pytest.skip("app.tasks not yet implemented")

    from fastapi import HTTPException

    user = _make_user()
    team_id = uuid.uuid4()

    async def _raise_404() -> None:
        raise HTTPException(status_code=404, detail="Team not found")

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with patch("app.auth.dependencies.redis_client", mock_redis):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_team_membership] = _raise_404

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user.id), 'user')}"},
            ) as ac:
                resp = await ac.get(f"/teams/{team_id}/tasks")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_task_without_permission_403() -> None:
    """PATCH /teams/{id}/tasks/{task_id}: без прав (не assignee/creator/manager) → 403."""
    if not _TASKS_AVAILABLE:
        pytest.skip("app.tasks not yet implemented")

    from fastapi import HTTPException

    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    task_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    member = _make_member(team_id, user_id, TeamRole.MEMBER)
    task = _make_task(task_id=task_id, team_id=team_id, creator_id=uuid.uuid4())  # другой creator

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    async def _raise_403() -> None:
        raise HTTPException(status_code=403, detail="Not authorized to edit this task")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with patch("app.auth.dependencies.redis_client", mock_redis):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_team_membership] = lambda: member
        app.dependency_overrides[require_task_editor] = _raise_403

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.patch(
                    f"/teams/{team_id}/tasks/{task_id}",
                    json={"title": "Hacked"},
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_require_task_editor_rejects_non_editor() -> None:
    """require_task_editor: участник без прав (не assignee/creator/manager) → 403."""
    if not _TASKS_AVAILABLE:
        pytest.skip("app.tasks not yet implemented")

    from fastapi import HTTPException

    from app.tasks.dependencies import require_task_editor

    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _make_task(team_id=team_id, creator_id=uuid.uuid4())  # другой creator
    membership = _make_member(team_id, user_id, TeamRole.MEMBER)
    user = _make_user(UserRole.USER, user_id)

    with pytest.raises(HTTPException) as exc_info:
        await require_task_editor(task=task, membership=membership, current_user=user)
    assert exc_info.value.status_code == 403
    assert "Not authorized" in exc_info.value.detail


@pytest.mark.asyncio
async def test_require_task_editor_allows_creator() -> None:
    """require_task_editor: creator задачи пропускается."""
    if not _TASKS_AVAILABLE:
        pytest.skip("app.tasks not yet implemented")

    from app.tasks.dependencies import require_task_editor

    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _make_task(team_id=team_id, creator_id=user_id)
    membership = _make_member(team_id, user_id, TeamRole.MEMBER)
    user = _make_user(UserRole.USER, user_id)

    result = await require_task_editor(task=task, membership=membership, current_user=user)
    assert result is task


@pytest.mark.asyncio
async def test_require_task_editor_allows_manager() -> None:
    """require_task_editor: manager команды пропускается."""
    if not _TASKS_AVAILABLE:
        pytest.skip("app.tasks not yet implemented")

    from app.tasks.dependencies import require_task_editor

    team_id = uuid.uuid4()
    user_id = uuid.uuid4()
    task = _make_task(team_id=team_id, creator_id=uuid.uuid4())  # другой creator
    membership = _make_member(team_id, user_id, TeamRole.MANAGER)
    user = _make_user(UserRole.USER, user_id)

    result = await require_task_editor(task=task, membership=membership, current_user=user)
    assert result is task


# ---------------------------------------------------------------------------
# Интеграционные тесты (требуют Docker-инфраструктуры)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_task_crud(async_engine: object, client: AsyncClient) -> None:
    """TASK-01: CRUD задач + soft-delete через HTTP-эндпоинты."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    hasher = PasswordHash((Argon2Hasher(),))
    created_user_ids: list[uuid.UUID] = []

    async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
        owner = User(
            email="task_crud_owner@example.com",
            password_hash=hasher.hash("TestPassword1!"),
            role=UserRole.USER,
            is_active=True,
        )
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        created_user_ids.append(owner.id)

    owner_token = create_access_token(str(owner.id), "user")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    try:
        # Создание команды
        create_team_resp = await client.post(
            "/teams", json={"name": "Task CRUD Team"}, headers=owner_headers
        )
        assert create_team_resp.status_code == 201, create_team_resp.text
        team_id = create_team_resp.json()["id"]

        # Создание задачи → 201
        create_task_resp = await client.post(
            f"/teams/{team_id}/tasks",
            json={"title": "My Task", "description": "Details"},
            headers=owner_headers,
        )
        assert create_task_resp.status_code == 201, create_task_resp.text
        task_data = create_task_resp.json()
        task_id = task_data["id"]
        assert task_data["status"] == "open"
        assert task_data["title"] == "My Task"

        # GET список — задача присутствует
        list_resp = await client.get(f"/teams/{team_id}/tasks", headers=owner_headers)
        assert list_resp.status_code == 200, list_resp.text
        tasks = list_resp.json()
        task_ids = [t["id"] for t in tasks]
        assert task_id in task_ids

        # GET detail — задача с комментариями
        detail_resp = await client.get(f"/teams/{team_id}/tasks/{task_id}", headers=owner_headers)
        assert detail_resp.status_code == 200, detail_resp.text
        assert detail_resp.json()["id"] == task_id

        # PATCH: обновление названия
        patch_resp = await client.patch(
            f"/teams/{team_id}/tasks/{task_id}",
            json={"title": "Updated Task"},
            headers=owner_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text
        assert patch_resp.json()["title"] == "Updated Task"

        # PATCH: переход статуса open → in_progress
        status_resp = await client.patch(
            f"/teams/{team_id}/tasks/{task_id}",
            json={"status": "in_progress"},
            headers=owner_headers,
        )
        assert status_resp.status_code == 200, status_resp.text
        assert status_resp.json()["status"] == "in_progress"

        # PATCH: open → done (должно вернуть 422, но задача уже in_progress)
        # Создадим новую задачу для проверки open→done
        task2_resp = await client.post(
            f"/teams/{team_id}/tasks",
            json={"title": "Task 2"},
            headers=owner_headers,
        )
        assert task2_resp.status_code == 201
        task2_id = task2_resp.json()["id"]

        invalid_status_resp = await client.patch(
            f"/teams/{team_id}/tasks/{task2_id}",
            json={"status": "done"},
            headers=owner_headers,
        )
        assert invalid_status_resp.status_code == 422, invalid_status_resp.text

        # DELETE → soft-delete
        delete_resp = await client.delete(
            f"/teams/{team_id}/tasks/{task_id}", headers=owner_headers
        )
        assert delete_resp.status_code == 200, delete_resp.text

        # После soft-delete задача не видна в списке
        list_after_resp = await client.get(f"/teams/{team_id}/tasks", headers=owner_headers)
        assert list_after_resp.status_code == 200
        ids_after = [t["id"] for t in list_after_resp.json()]
        assert task_id not in ids_after, "Soft-deleted задача не должна быть в списке"

        # После soft-delete detail → 404
        detail_after_resp = await client.get(
            f"/teams/{team_id}/tasks/{task_id}", headers=owner_headers
        )
        assert detail_after_resp.status_code == 404, "Soft-deleted задача должна вернуть 404"

    finally:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            for uid in created_user_ids:
                await session.execute(delete(User).where(User.id == uid))
            await session.commit()


@pytest.mark.integration
async def test_task_detail_comments(async_engine: object, client: AsyncClient) -> None:
    """TASK-05: GET /teams/{id}/tasks/{id} содержит вложенный массив comments."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    hasher = PasswordHash((Argon2Hasher(),))
    created_user_ids: list[uuid.UUID] = []

    async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
        owner = User(
            email="task_comments_owner@example.com",
            password_hash=hasher.hash("TestPassword1!"),
            role=UserRole.USER,
            is_active=True,
        )
        session.add(owner)
        await session.commit()
        await session.refresh(owner)
        created_user_ids.append(owner.id)

    owner_token = create_access_token(str(owner.id), "user")
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    try:
        # Создание команды и задачи
        team_resp = await client.post(
            "/teams", json={"name": "Comment Test Team"}, headers=owner_headers
        )
        assert team_resp.status_code == 201
        team_id = team_resp.json()["id"]

        task_resp = await client.post(
            f"/teams/{team_id}/tasks", json={"title": "Task with comments"}, headers=owner_headers
        )
        assert task_resp.status_code == 201
        task_id = task_resp.json()["id"]

        # Detail до комментариев → пустой массив comments
        detail_before = await client.get(
            f"/teams/{team_id}/tasks/{task_id}", headers=owner_headers
        )
        assert detail_before.status_code == 200
        assert detail_before.json()["comments"] == []

        # POST comment
        comment_resp = await client.post(
            f"/teams/{team_id}/tasks/{task_id}/comments",
            json={"body": "Первый комментарий"},
            headers=owner_headers,
        )
        assert comment_resp.status_code == 201, comment_resp.text
        comment_data = comment_resp.json()
        assert comment_data["body"] == "Первый комментарий"

        # GET detail после комментария → comments непустой
        detail_after = await client.get(
            f"/teams/{team_id}/tasks/{task_id}", headers=owner_headers
        )
        assert detail_after.status_code == 200
        comments = detail_after.json()["comments"]
        assert len(comments) >= 1, "detail.comments должен содержать хотя бы один комментарий"
        bodies = [c["body"] for c in comments]
        assert "Первый комментарий" in bodies

    finally:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            for uid in created_user_ids:
                await session.execute(delete(User).where(User.id == uid))
            await session.commit()


@pytest.mark.integration
async def test_task_non_member_access(async_engine: object, client: AsyncClient) -> None:
    """Не-член команды получает 404 при GET /teams/{id}/tasks (анти-энумерация)."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    hasher = PasswordHash((Argon2Hasher(),))
    created_ids: list[uuid.UUID] = []

    async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
        owner = User(
            email="nm_task_owner@example.com",
            password_hash=hasher.hash("TestPassword1!"),
            role=UserRole.USER,
            is_active=True,
        )
        outsider = User(
            email="nm_task_outsider@example.com",
            password_hash=hasher.hash("TestPassword1!"),
            role=UserRole.USER,
            is_active=True,
        )
        session.add_all([owner, outsider])
        await session.commit()
        for u in [owner, outsider]:
            await session.refresh(u)
        created_ids = [owner.id, outsider.id]

    try:
        owner_headers = {
            "Authorization": f"Bearer {create_access_token(str(owner.id), 'user')}"
        }
        outsider_headers = {
            "Authorization": f"Bearer {create_access_token(str(outsider.id), 'user')}"
        }

        team_resp = await client.post(
            "/teams", json={"name": "NM Access Team"}, headers=owner_headers
        )
        assert team_resp.status_code == 201
        team_id = team_resp.json()["id"]

        # Outsider (не член) получает 404
        outsider_list = await client.get(f"/teams/{team_id}/tasks", headers=outsider_headers)
        assert outsider_list.status_code == 404, outsider_list.text

    finally:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            for uid in created_ids:
                await session.execute(delete(User).where(User.id == uid))
            await session.commit()
