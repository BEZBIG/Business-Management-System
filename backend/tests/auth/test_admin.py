"""Тесты SQLAdmin панели: auth-gate, redirect, отклонение не-admin."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin.setup import AdminAuthBackend
from app.auth.models import User, UserRole


@pytest.mark.asyncio
async def test_admin_redirect_unauthenticated() -> None:
    """GET /admin/ без авторизации должен вернуть редирект на страницу логина (302/307).

    SQLAdmin AuthenticationBackend защищает все /admin/* маршруты.
    Клиент создаётся без сессионного cookie — имитирует анонимный браузер.
    """
    from app.main import app  # noqa: PLC0415

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as ac:
        response = await ac.get("/admin/")

    assert response.status_code in (302, 307), (
        f"Expected redirect (302/307) for unauthenticated /admin/, got {response.status_code}"
    )


@pytest.mark.asyncio
async def test_admin_login_non_admin() -> None:
    """AdminAuthBackend.login() с пользователем role=user должен вернуть False.

    AuthenticationBackend.login() проверяет role==admin;
    role=user отклоняется без создания сессии.
    """
    # Создаём user-роль пользователя (активен, пароль верный, но не admin)
    non_admin_user = MagicMock(spec=User)
    non_admin_user.is_active = True
    non_admin_user.role = UserRole.USER
    non_admin_user.email = "user@example.com"
    non_admin_user.password_hash = "hashed_password"

    # Мок request со вшитой формой: username + password
    mock_form = {"username": "user@example.com", "password": "ValidPass123!"}
    mock_request = MagicMock()
    mock_request.form = AsyncMock(return_value=mock_form)
    mock_request.session = {}

    # Мок сессионного контекста БД → возвращает non_admin_user
    mock_session = AsyncMock()
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

    backend = AdminAuthBackend(secret_key="test-secret-key-32-chars-xxxxxxxx")

    with (
        patch("app.admin.setup.async_session_factory", return_value=mock_session_ctx),
        patch("app.admin.setup.get_user_by_email", AsyncMock(return_value=non_admin_user)),
        patch(
            "app.admin.setup.password_hasher.verify",
            return_value=True,  # пароль верный — но роль не admin
        ),
    ):
        result = await backend.login(mock_request)

    assert result is False, "non-admin user must not pass AdminAuthBackend.login()"
