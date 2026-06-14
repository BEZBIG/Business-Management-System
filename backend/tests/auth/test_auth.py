"""Тесты эндпоинтов аутентификации и RBAC — RED-стадия (Nyquist Wave 0)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient) -> None:
    """POST /auth/register с валидными данными должен вернуть 201 и access_token.

    AUTH-01: регистрация нового пользователя с уникальным email и сильным паролем.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: POST /auth/register")


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    """POST /auth/register с уже существующим email должен вернуть 409.

    AUTH-01: уникальность email гарантируется на уровне БД и сервиса.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: дублирующий email → 409")


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient) -> None:
    """POST /auth/register со слабым паролем (< 12 символов / без спецсимволов) должен вернуть 422.

    AUTH-01 + D-04: политика пароля валидируется Pydantic-схемой до записи в БД.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: слабый пароль → 422")


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """POST /auth/login с верными credentials должен вернуть access_token и установить refresh cookie.

    AUTH-02: вход с JWT access 15 мин (HS256) + refresh в HttpOnly cookie.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: POST /auth/login → JWT + refresh cookie")


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    """POST /auth/login с неверным паролем должен вернуть 401 с единым сообщением 'Invalid credentials'.

    AUTH-02 + anti-enumeration: одно сообщение для несуществующего email и неверного пароля.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: неверный пароль → 401 anti-enumeration")


@pytest.mark.asyncio
async def test_logout_revokes_token(client: AsyncClient) -> None:
    """POST /auth/logout должен добавить jti в Redis revocation-set и удалить refresh cookie.

    AUTH-03 (D-08): jti записывается в Redis с TTL = остаток жизни токена; повторный запрос с тем же токеном → 401.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: logout → jti в Redis, повторный запрос → 401")


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient) -> None:
    """POST /auth/refresh с валидным refresh cookie должен вернуть новый access_token.

    AUTH-04 (D-07): обновление access-токена без повторного логина.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: refresh cookie → новый access_token")


@pytest.mark.asyncio
async def test_rbac_user_forbidden(auth_client: AsyncClient) -> None:
    """Запрос с ролью user к защищённому admin-эндпоинту должен вернуть 403.

    AUTH-05 (D-12 уровень 1): route-зависимость require_role('admin') отклоняет запросы с role=user.
    """
    raise NotImplementedError("Реализовать в Plan 02-03: user → 403 на admin-эндпоинт")


@pytest.mark.asyncio
async def test_rbac_db_layer(auth_client: AsyncClient) -> None:
    """Принципал с ролью user, запрашивающий ресурс другого пользователя по чужому id, должен получить 404.

    AUTH-05 (D-12 уровень 2 — DB-layer RBAC, anti-enumeration):
    - Возвращается 404, а не 403, чтобы не раскрывать существование ресурса.
    - Реализуется через owner-scoped helper из Plan 02-02, проверяется в Plan 02-03.
    - Пример: GET /users/{other_user_id} → 404 для role=user.
    """
    raise NotImplementedError(
        "Реализовать в Plan 02-03 после owner-scoped helper из Plan 02-02: "
        "user → 404 при запросе чужого ресурса (anti-enumeration)"
    )


@pytest.mark.asyncio
async def test_get_me(auth_client: AsyncClient) -> None:
    """GET /users/me должен вернуть профиль текущего пользователя (200).

    AUTH-06 (D-13): просмотр профиля — id, email, role, is_active, created_at.
    """
    raise NotImplementedError("Реализовать в Plan 02-02: GET /users/me → профиль")


@pytest.mark.asyncio
async def test_change_password_wrong_current(auth_client: AsyncClient) -> None:
    """PATCH /users/me/password с неверным current_password должен вернуть 400.

    AUTH-07 (D-05): новый пароль не сохраняется при несовпадении текущего.
    """
    raise NotImplementedError(
        "Реализовать в Plan 02-02: неверный current_password → 400, новый хеш не пишется"
    )
