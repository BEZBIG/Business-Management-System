"""Тесты SQLAdmin панели — RED-стадия (Nyquist Wave 0)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_redirect_unauthenticated(client: AsyncClient) -> None:
    """GET /admin/ без авторизации должен вернуть редирект на страницу логина (302/307).

    ADMIN-01 (D-14): SQLAdmin AuthenticationBackend защищает все /admin/* маршруты.
    """
    raise NotImplementedError("Реализовать в Plan 02-04: GET /admin/ без сессии → redirect 302/307")


@pytest.mark.asyncio
async def test_admin_login_non_admin(client: AsyncClient) -> None:
    """POST /admin/login с пользователем role=user должен отклонить вход.

    ADMIN-01 (D-14): AuthenticationBackend.login() проверяет role==admin; role=user отклоняется.
    """
    raise NotImplementedError("Реализовать в Plan 02-04: non-admin user → вход в SQLAdmin отклонён")
