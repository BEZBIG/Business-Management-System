"""Тесты HTTP-роутера команд.

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
    from app.teams.dependencies import get_team_membership
    from app.teams.models import Team, TeamMember, TeamRole

    _TEAMS_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _TEAMS_AVAILABLE = False


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


def _make_team(team_id: uuid.UUID | None = None, invite_code: str = "code123") -> Team:
    """Создаёт Team без сохранения в БД."""
    t = Team(name="Test Team", invite_code=invite_code)
    t.id = team_id or uuid.uuid4()
    t.created_at = datetime.now(UTC)
    return t


# ---------------------------------------------------------------------------
# Unit-тесты (без живой БД — DI-override)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_teams_creates_team() -> None:
    """POST /teams создаёт команду и возвращает 201 + TeamResponse с invite_code."""
    if not _TEAMS_AVAILABLE:
        pytest.skip("app.teams not yet implemented")

    user_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    team_id = uuid.uuid4()
    team = _make_team(team_id, "generatedcode123")

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.teams.router.create_team", return_value=team),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.post("/teams", json={"name": "New Team"})
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["invite_code"] == "generatedcode123"
    assert body["name"] == "Test Team"


@pytest.mark.asyncio
async def test_get_team_non_member_returns_404() -> None:
    """GET /teams/{id}: не-член команды получает 404 (анти-энумерация)."""
    if not _TEAMS_AVAILABLE:
        pytest.skip("app.teams not yet implemented")

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
                resp = await ac.get(f"/teams/{team_id}")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_join_team_valid_code() -> None:
    """POST /teams/{id}/join с верным кодом → 200 + TeamMemberResponse."""
    if not _TEAMS_AVAILABLE:
        pytest.skip("app.teams not yet implemented")

    user_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    team_id = uuid.uuid4()
    member = _make_member(team_id, user_id, TeamRole.MEMBER)

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.teams.router.join_team", return_value=member),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.post(f"/teams/{team_id}/join", json={"code": "validcode"})
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["team_id"] == str(team_id)
    assert body["role"] == "member"


@pytest.mark.asyncio
async def test_join_team_invalid_code() -> None:
    """POST /teams/{id}/join с неверным кодом → 400."""
    if not _TEAMS_AVAILABLE:
        pytest.skip("app.teams not yet implemented")

    user_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    team_id = uuid.uuid4()

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.teams.router.join_team", return_value=None),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.post(f"/teams/{team_id}/join", json={"code": "wrongcode"})
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_remove_member_rbac() -> None:
    """TEAM-03: remove_member: owner/manager пропускается; member → 403 через dependency."""
    if not _TEAMS_AVAILABLE:
        pytest.skip("app.teams not yet implemented")

    from fastapi import HTTPException

    team_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    target_id = uuid.uuid4()

    owner_membership = _make_member(team_id, owner_id, TeamRole.OWNER)
    member_membership = _make_member(team_id, member_id, TeamRole.MEMBER)

    # Тест 1: owner удаляет target → 200
    owner_user = _make_user(UserRole.USER, owner_id)
    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.teams.router.remove_member", return_value=True),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: owner_user
        app.dependency_overrides[get_team_membership] = lambda: owner_membership

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(owner_id), 'user')}"},
            ) as ac:
                resp = await ac.delete(f"/teams/{team_id}/members/{target_id}")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, f"owner должен получить 200: {resp.text}"

    # Тест 2: require_team_role(OWNER, MANAGER) возвращает 403 для MEMBER
    from app.teams.dependencies import require_team_role

    check_fn = require_team_role(TeamRole.OWNER, TeamRole.MANAGER)
    with pytest.raises(HTTPException) as exc_info:
        await check_fn(membership=member_membership)
    assert exc_info.value.status_code == 403
    assert "Insufficient team role" in exc_info.value.detail


@pytest.mark.asyncio
async def test_assign_role_rbac() -> None:
    """TEAM-04: назначение роли: owner → 200; member → 403 через dependency."""
    if not _TEAMS_AVAILABLE:
        pytest.skip("app.teams not yet implemented")

    from fastapi import HTTPException

    team_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    member_id = uuid.uuid4()
    target_id = uuid.uuid4()

    owner_membership = _make_member(team_id, owner_id, TeamRole.OWNER)
    member_membership = _make_member(team_id, member_id, TeamRole.MEMBER)
    target_membership = _make_member(team_id, target_id, TeamRole.MEMBER)

    # Тест 1: require_team_role пропускает owner
    from app.teams.dependencies import require_team_role

    check_fn = require_team_role(TeamRole.OWNER, TeamRole.MANAGER)
    result = await check_fn(membership=owner_membership)
    assert result is owner_membership, "owner должен быть пропущен require_team_role"

    # Тест 2: require_team_role возвращает 403 для MEMBER
    with pytest.raises(HTTPException) as exc_info:
        await check_fn(membership=member_membership)
    assert exc_info.value.status_code == 403

    # Тест 3: owner назначает роль через HTTP endpoint
    owner_user = _make_user(UserRole.USER, owner_id)
    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.teams.router.set_member_role", return_value=target_membership),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: owner_user
        app.dependency_overrides[get_team_membership] = lambda: owner_membership

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(owner_id), 'user')}"},
            ) as ac:
                resp = await ac.patch(
                    f"/teams/{team_id}/members/{target_id}/role",
                    json={"role": "manager"},
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, f"owner должен получить 200: {resp.text}"


# ---------------------------------------------------------------------------
# Интеграционные тесты (требуют Docker-инфраструктуры)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_join_team(async_engine: object, client: AsyncClient) -> None:
    """TEAM-02: POST /teams/{id}/join с верным кодом → 200; неверный → 400."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    hasher = PasswordHash((Argon2Hasher(),))

    async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
        creator = User(
            email="team_join_creator@example.com",
            password_hash=hasher.hash("TestPassword1!"),
            role=UserRole.USER,
            is_active=True,
        )
        session.add(creator)
        await session.commit()
        await session.refresh(creator)
        creator_id = creator.id

    creator_token = create_access_token(str(creator_id), "user")
    creator_headers = {"Authorization": f"Bearer {creator_token}"}

    try:
        create_resp = await client.post(
            "/teams",
            json={"name": "Join Test Team"},
            headers=creator_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        team_data = create_resp.json()
        team_id = team_data["id"]
        invite_code = team_data["invite_code"]

        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            joiner = User(
                email="team_join_joiner@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            session.add(joiner)
            await session.commit()
            await session.refresh(joiner)
            joiner_id = joiner.id

        joiner_token = create_access_token(str(joiner_id), "user")
        joiner_headers = {"Authorization": f"Bearer {joiner_token}"}

        try:
            # Неверный код → 400
            bad_resp = await client.post(
                f"/teams/{team_id}/join",
                json={"code": "wrongcode123"},
                headers=joiner_headers,
            )
            assert bad_resp.status_code == 400, bad_resp.text

            # Верный код → 200
            good_resp = await client.post(
                f"/teams/{team_id}/join",
                json={"code": invite_code},
                headers=joiner_headers,
            )
            assert good_resp.status_code == 200, good_resp.text
            join_data = good_resp.json()
            assert join_data["role"] == "member"
            assert join_data["team_id"] == team_id

            # Повторный join → 200 (идемпотентность)
            repeat_resp = await client.post(
                f"/teams/{team_id}/join",
                json={"code": invite_code},
                headers=joiner_headers,
            )
            assert repeat_resp.status_code == 200, repeat_resp.text

        finally:
            async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
                await session.execute(delete(User).where(User.id == joiner_id))
                await session.commit()

    finally:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            await session.execute(delete(User).where(User.id == creator_id))
            await session.commit()


@pytest.mark.integration
async def test_remove_member_rbac_integration(async_engine: object, client: AsyncClient) -> None:
    """TEAM-03: remove_member: owner/manager → 200; member → 403 (интеграционный)."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    hasher = PasswordHash((Argon2Hasher(),))
    created_ids: list[uuid.UUID] = []

    try:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            owner = User(
                email="team_owner_rbac@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            member = User(
                email="team_member_rbac@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            target = User(
                email="team_target_rbac@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            session.add_all([owner, member, target])
            await session.commit()
            for u in [owner, member, target]:
                await session.refresh(u)
            created_ids = [owner.id, member.id, target.id]

        owner_headers = {"Authorization": f"Bearer {create_access_token(str(owner.id), 'user')}"}
        member_headers = {"Authorization": f"Bearer {create_access_token(str(member.id), 'user')}"}

        create_resp = await client.post(
            "/teams", json={"name": "RBAC Test Team"}, headers=owner_headers
        )
        assert create_resp.status_code == 201, create_resp.text
        team_data = create_resp.json()
        team_id = team_data["id"]
        invite_code = team_data["invite_code"]

        for tok in [
            create_access_token(str(member.id), "user"),
            create_access_token(str(target.id), "user"),
        ]:
            jr = await client.post(
                f"/teams/{team_id}/join",
                json={"code": invite_code},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert jr.status_code == 200, jr.text

        # member → 403
        member_del = await client.delete(
            f"/teams/{team_id}/members/{target.id}", headers=member_headers
        )
        assert member_del.status_code == 403, member_del.text

        # owner → 200
        owner_del = await client.delete(
            f"/teams/{team_id}/members/{target.id}", headers=owner_headers
        )
        assert owner_del.status_code == 200, owner_del.text

    finally:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            for uid in created_ids:
                await session.execute(delete(User).where(User.id == uid))
            await session.commit()


@pytest.mark.integration
async def test_assign_role_rbac_integration(async_engine: object, client: AsyncClient) -> None:
    """TEAM-04: назначение роли: owner → 200; member → 403 (интеграционный)."""
    from pwdlib import PasswordHash
    from pwdlib.hashers.argon2 import Argon2Hasher
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    hasher = PasswordHash((Argon2Hasher(),))
    created_ids: list[uuid.UUID] = []

    try:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            owner = User(
                email="role_owner_rbac@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            member = User(
                email="role_member_rbac@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            target = User(
                email="role_target_rbac@example.com",
                password_hash=hasher.hash("TestPassword1!"),
                role=UserRole.USER,
                is_active=True,
            )
            session.add_all([owner, member, target])
            await session.commit()
            for u in [owner, member, target]:
                await session.refresh(u)
            created_ids = [owner.id, member.id, target.id]

        owner_headers = {"Authorization": f"Bearer {create_access_token(str(owner.id), 'user')}"}
        member_headers = {"Authorization": f"Bearer {create_access_token(str(member.id), 'user')}"}

        create_resp = await client.post(
            "/teams", json={"name": "Role RBAC Team"}, headers=owner_headers
        )
        assert create_resp.status_code == 201, create_resp.text
        team_data = create_resp.json()
        team_id = team_data["id"]
        invite_code = team_data["invite_code"]

        for tok in [
            create_access_token(str(member.id), "user"),
            create_access_token(str(target.id), "user"),
        ]:
            jr = await client.post(
                f"/teams/{team_id}/join",
                json={"code": invite_code},
                headers={"Authorization": f"Bearer {tok}"},
            )
            assert jr.status_code == 200, jr.text

        # member → 403
        member_patch = await client.patch(
            f"/teams/{team_id}/members/{target.id}/role",
            json={"role": "manager"},
            headers=member_headers,
        )
        assert member_patch.status_code == 403, member_patch.text

        # owner → 200
        owner_patch = await client.patch(
            f"/teams/{team_id}/members/{target.id}/role",
            json={"role": "manager"},
            headers=owner_headers,
        )
        assert owner_patch.status_code == 200, owner_patch.text
        assert owner_patch.json()["role"] == "manager"

    finally:
        async with AsyncSession(async_engine) as session:  # type: ignore[arg-type]
            for uid in created_ids:
                await session.execute(delete(User).where(User.id == uid))
            await session.commit()
