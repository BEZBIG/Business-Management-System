"""Фикстуры pytest для auth-тестов: test_user, test_admin_user, auth_client, mock_redis_jti."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

try:
    from app.auth.models import User, UserRole  # noqa: PLC0415
    from app.auth.security import create_access_token  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    _AUTH_AVAILABLE = True
except ModuleNotFoundError:
    _AUTH_AVAILABLE = False


@pytest.fixture
def mock_redis_jti() -> AsyncMock:
    """Мок Redis для jti-blacklist: exists() всегда 0 (токен не отозван), set() возвращает True."""
    mock = AsyncMock()
    mock.exists.return_value = 0
    mock.set.return_value = True
    return mock


@pytest.fixture
async def test_user(async_engine: AsyncEngine) -> AsyncGenerator[User, None]:
    """Создаёт тестового пользователя в БД (role=user) и удаляет после теста."""
    if not _AUTH_AVAILABLE:
        pytest.skip("app.auth not yet implemented")
        return

    from pwdlib import PasswordHash  # noqa: PLC0415
    from pwdlib.hashers.argon2 import Argon2Hasher  # noqa: PLC0415
    from sqlalchemy import delete  # noqa: PLC0415

    hasher = PasswordHash((Argon2Hasher(),))
    password_hash = hasher.hash("TestPassword1!")

    async with AsyncSession(async_engine) as session:
        user = User(
            email="testuser@example.com",
            password_hash=password_hash,
            role=UserRole.USER,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_id = user.id

    yield user  # type: ignore[misc]

    async with AsyncSession(async_engine) as session:
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


@pytest.fixture
async def test_admin_user(async_engine: AsyncEngine) -> AsyncGenerator[User, None]:
    """Создаёт тестового администратора в БД (role=admin) и удаляет после теста."""
    if not _AUTH_AVAILABLE:
        pytest.skip("app.auth not yet implemented")
        return

    from pwdlib import PasswordHash  # noqa: PLC0415
    from pwdlib.hashers.argon2 import Argon2Hasher  # noqa: PLC0415
    from sqlalchemy import delete  # noqa: PLC0415

    hasher = PasswordHash((Argon2Hasher(),))
    password_hash = hasher.hash("AdminPassword1!")

    async with AsyncSession(async_engine) as session:
        admin = User(
            email="testadmin@example.com",
            password_hash=password_hash,
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        admin_id = admin.id

    yield admin  # type: ignore[misc]

    async with AsyncSession(async_engine) as session:
        await session.execute(delete(User).where(User.id == admin_id))
        await session.commit()


@pytest.fixture
async def auth_client(test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient с Bearer-токеном тестового пользователя (role=user)."""
    if not _AUTH_AVAILABLE:
        pytest.skip("app.auth not yet implemented")
        return

    access_token = create_access_token(
        sub=str(test_user.id),
        role=test_user.role.value,
    )

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as ac:
        yield ac
