"""Тесты аутентификации и RBAC.

Unit-тесты security/schemas/service/dependencies (Plan 02-02) и
HTTP endpoint-стабы (реализуются в Plan 02-03).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import AsyncClient
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Task 1: security.py — unit-тесты (password hash/verify + JWT encode/decode)
# ---------------------------------------------------------------------------


def test_password_hash_and_verify() -> None:
    """password_hasher.verify верно работает при верном и неверном паролях."""
    from app.auth.security import password_hasher

    hashed = password_hasher.hash("Str0ng!Passw0rd")
    assert password_hasher.verify("Str0ng!Passw0rd", hashed) is True
    assert password_hasher.verify("WrongPassword1!", hashed) is False


def test_access_token_claims() -> None:
    """decode_access_token возвращает верные claims: sub, role, jti, type=access."""
    from app.auth.security import create_access_token, decode_access_token

    token = create_access_token("user-id-123", "user")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-id-123"
    assert payload["role"] == "user"
    assert payload["type"] == "access"
    assert "jti" in payload and payload["jti"]


def test_token_wrong_secret_raises() -> None:
    """decode_access_token с другим секретом бросает jwt.InvalidTokenError (T-02-04)."""
    from app.auth.security import ALGORITHM, create_access_token

    token = create_access_token("u1", "user")
    with pytest.raises(jwt.InvalidTokenError):
        jwt.decode(token, "wrong-secret", algorithms=[ALGORITHM])


def test_expired_token_raises() -> None:
    """Просроченный токен бросает jwt.ExpiredSignatureError."""
    import time

    from app.auth.security import ALGORITHM, decode_access_token
    from app.core.config import settings

    now = int(time.time()) - 100
    payload = {
        "sub": "u1",
        "role": "user",
        "jti": "abc",
        "iat": now,
        "exp": now - 10,
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_refresh_token_type() -> None:
    """create_refresh_token создаёт токен с type=refresh."""
    from app.auth.security import create_refresh_token, decode_refresh_token

    token = create_refresh_token("user-id-456")
    payload = decode_refresh_token(token)
    assert payload["sub"] == "user-id-456"
    assert payload["type"] == "refresh"
    assert "jti" in payload


# ---------------------------------------------------------------------------
# Task 2: schemas.py — unit-тесты валидации пароля и UserMeResponse
# ---------------------------------------------------------------------------


def test_register_request_short_password() -> None:
    """RegisterRequest с паролем < 12 символов → ValidationError (D-04)."""
    from app.auth.schemas import RegisterRequest

    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", password="short")


def test_register_request_no_uppercase() -> None:
    """RegisterRequest без верхнего регистра → ValidationError (D-04)."""
    from app.auth.schemas import RegisterRequest

    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", password="alllowercase1!")


def test_register_request_no_digit() -> None:
    """RegisterRequest без цифры → ValidationError (D-04)."""
    from app.auth.schemas import RegisterRequest

    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", password="NoDigitInPass!!")


def test_register_request_no_special() -> None:
    """RegisterRequest без спецсимвола → ValidationError (D-04)."""
    from app.auth.schemas import RegisterRequest

    with pytest.raises(ValidationError):
        RegisterRequest(email="a@b.co", password="NoSpecial1234AB")


def test_register_request_valid() -> None:
    """RegisterRequest с сильным паролем проходит валидацию."""
    from app.auth.schemas import RegisterRequest

    req = RegisterRequest(email="a@b.co", password="Str0ng!Passw0rd")
    assert req.email == "a@b.co"
    assert req.password == "Str0ng!Passw0rd"


def test_user_me_response_no_password_hash() -> None:
    """UserMeResponse не содержит поля password_hash (T-02-09)."""
    import datetime

    from app.auth.schemas import UserMeResponse

    resp = UserMeResponse(
        id=uuid.uuid4(),
        email="u@example.com",
        role="user",
        is_active=True,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    data = resp.model_dump()
    assert "password_hash" not in data


def test_password_change_request_validates_new_password() -> None:
    """PasswordChangeRequest валидирует new_password (D-04/D-05)."""
    from app.auth.schemas import PasswordChangeRequest

    with pytest.raises(ValidationError):
        PasswordChangeRequest(current_password="anything", new_password="weak")

    valid = PasswordChangeRequest(
        current_password="OldPass1!OldPass",
        new_password="NewStr0ng!Pass1",
    )
    assert valid.new_password == "NewStr0ng!Pass1"


# ---------------------------------------------------------------------------
# Task 2: service.py — unit-тесты (mock-based, без реальной БД)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_user_returns_none_on_wrong_password() -> None:
    """authenticate_user возвращает None при неверном пароле (anti-enumeration, T-02-07)."""
    from unittest.mock import AsyncMock

    from app.auth.models import User, UserRole
    from app.auth.security import password_hasher
    from app.auth.service import authenticate_user

    mock_session = AsyncMock()
    user = User(
        email="u@example.com",
        password_hash=password_hasher.hash("CorrectPass1!"),
        role=UserRole.USER,
        is_active=True,
    )
    user.id = uuid.uuid4()

    with patch("app.auth.service.get_user_by_email", return_value=user):
        result = await authenticate_user(mock_session, "u@example.com", "WrongPass1!")
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_user_returns_none_for_unknown_email() -> None:
    """authenticate_user возвращает None при несуществующем email (anti-enumeration)."""
    from unittest.mock import AsyncMock

    from app.auth.service import authenticate_user

    mock_session = AsyncMock()
    with patch("app.auth.service.get_user_by_email", return_value=None):
        result = await authenticate_user(mock_session, "nobody@example.com", "AnyPass1!")
    assert result is None


@pytest.mark.asyncio
async def test_create_user_assigns_role_user() -> None:
    """create_user всегда назначает role=USER на сервере (D-10, T-02-08)."""
    from unittest.mock import AsyncMock

    from app.auth.models import UserRole
    from app.auth.service import create_user

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    captured = {}

    def capture_add(obj):
        captured["user"] = obj

    mock_session.add = capture_add

    with patch("app.auth.service.get_user_by_email", return_value=None):
        await create_user(mock_session, "new@example.com", "Str0ng!Passw0rd")

    assert captured["user"].role == UserRole.USER
    assert captured["user"].email == "new@example.com"
    # password_hash должен быть установлен (не оригинальный пароль)
    assert captured["user"].password_hash != "Str0ng!Passw0rd"
    assert len(captured["user"].password_hash) > 20


@pytest.mark.asyncio
async def test_change_password_wrong_current_returns_false() -> None:
    """change_password при неверном current_password → False; хеш не меняется (D-05)."""
    from app.auth.models import User, UserRole
    from app.auth.security import password_hasher
    from app.auth.service import change_password

    mock_session = AsyncMock()
    original_hash = password_hasher.hash("OriginalPass1!")
    user = User(
        email="u@example.com",
        password_hash=original_hash,
        role=UserRole.USER,
        is_active=True,
    )
    user.id = uuid.uuid4()

    result = await change_password(mock_session, user, "WrongCurrent1!", "NewPass1!AB")
    assert result is False
    # Хеш не должен измениться
    assert user.password_hash == original_hash


@pytest.mark.asyncio
async def test_seed_first_superuser_idempotent() -> None:
    """seed_first_superuser не создаёт дубликат, если пользователь уже существует (D-11)."""
    from app.auth.models import User, UserRole
    from app.auth.service import seed_first_superuser

    mock_session = AsyncMock()
    existing_admin = User(
        email="admin@example.com",
        password_hash="somehash",
        role=UserRole.ADMIN,
        is_active=True,
    )

    with (
        patch("app.auth.service.settings") as mock_settings,
        patch("app.auth.service.get_user_by_email", return_value=existing_admin),
    ):
        mock_settings.first_superuser_email = "admin@example.com"
        mock_settings.first_superuser_password = "AdminPass1!"
        await seed_first_superuser(mock_session)

    # session.add не должен вызываться — пользователь уже существует
    mock_session.add.assert_not_called()


# ---------------------------------------------------------------------------
# Task 2: service.py — DB-layer RBAC get_user_for_principal (D-12 уровень 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_db_layer_principal_user_cannot_access_other() -> None:
    """get_user_for_principal: user-принципал с чужим target_id → None (D-12 уровень 2, T-02-22)."""
    from app.auth.models import User, UserRole
    from app.auth.service import get_user_for_principal

    mock_session = AsyncMock()
    principal = User(email="me@example.com", password_hash="h", role=UserRole.USER, is_active=True)
    principal.id = uuid.uuid4()

    other_id = uuid.uuid4()
    result = await get_user_for_principal(mock_session, other_id, principal)
    assert result is None
    # session.get не должен вызываться для чужого ресурса
    mock_session.get.assert_not_called()


@pytest.mark.asyncio
async def test_db_layer_principal_user_can_access_own() -> None:
    """get_user_for_principal: user-принципал со своим id → возвращает User."""
    from app.auth.models import User, UserRole
    from app.auth.service import get_user_for_principal

    own_id = uuid.uuid4()
    principal = User(email="me@example.com", password_hash="h", role=UserRole.USER, is_active=True)
    principal.id = own_id

    mock_session = AsyncMock()
    mock_session.get.return_value = principal

    result = await get_user_for_principal(mock_session, own_id, principal)
    assert result is principal


@pytest.mark.asyncio
async def test_db_layer_admin_can_access_any() -> None:
    """get_user_for_principal: admin-принципал → возвращает любую строку."""
    from app.auth.models import User, UserRole
    from app.auth.service import get_user_for_principal

    admin = User(email="admin@example.com", password_hash="h", role=UserRole.ADMIN, is_active=True)
    admin.id = uuid.uuid4()

    other_user = User(
        email="other@example.com", password_hash="h", role=UserRole.USER, is_active=True
    )
    other_user.id = uuid.uuid4()

    mock_session = AsyncMock()
    mock_session.get.return_value = other_user

    result = await get_user_for_principal(mock_session, other_user.id, admin)
    assert result is other_user


# ---------------------------------------------------------------------------
# Task 3: dependencies.py — unit-тесты get_current_user + require_role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_current_user_no_credentials() -> None:
    """get_current_user без Authorization → 401."""
    from fastapi import HTTPException

    from app.auth.dependencies import get_current_user

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=None, session=AsyncMock())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_expired_token() -> None:
    """get_current_user с просроченным токеном → 401 'Token expired'."""
    import time
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.auth.dependencies import get_current_user
    from app.auth.security import ALGORITHM
    from app.core.config import settings

    now = int(time.time()) - 200
    payload = {
        "sub": str(uuid.uuid4()),
        "role": "user",
        "jti": "testjti",
        "iat": now,
        "exp": now - 10,
        "type": "access",
    }
    expired_token = jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    credentials = SimpleNamespace(credentials=expired_token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, session=AsyncMock())  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_current_user_refresh_token_rejected() -> None:
    """get_current_user с refresh-токеном (type=refresh) → 401 (type mismatch)."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.auth.dependencies import get_current_user
    from app.auth.security import create_refresh_token

    refresh_token = create_refresh_token("some-user-id")
    credentials = SimpleNamespace(credentials=refresh_token)

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, session=AsyncMock())  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_revoked_jti() -> None:
    """get_current_user с отозванным jti (redis exists → 1) → 401 'Token revoked' (D-08)."""
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.auth.dependencies import get_current_user
    from app.auth.security import create_access_token

    token = create_access_token("some-user-id", "user")
    credentials = SimpleNamespace(credentials=token)

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 1  # jti в blacklist

    with patch("app.auth.dependencies.redis_client", mock_redis):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=credentials, session=AsyncMock())  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401
    assert "revoked" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_current_user_valid_token_returns_user() -> None:
    """get_current_user с валидным токеном и активным пользователем → возвращает User."""
    from types import SimpleNamespace

    from app.auth.dependencies import get_current_user
    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token

    user_id = uuid.uuid4()
    user = User(email="u@example.com", password_hash="h", role=UserRole.USER, is_active=True)
    user.id = user_id

    token = create_access_token(str(user_id), "user")
    credentials = SimpleNamespace(credentials=token)

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0  # не в blacklist

    mock_session = AsyncMock()
    mock_session.get.return_value = user

    with patch("app.auth.dependencies.redis_client", mock_redis):
        result = await get_current_user(credentials=credentials, session=mock_session)  # type: ignore[arg-type]
    assert result is user


@pytest.mark.asyncio
async def test_rbac_user_forbidden() -> None:
    """require_role('admin') для user-роли → 403 (D-12 уровень 1, T-02-22)."""
    from fastapi import HTTPException

    from app.auth.dependencies import require_role
    from app.auth.models import User, UserRole

    user = User(email="u@example.com", password_hash="h", role=UserRole.USER, is_active=True)
    user.id = uuid.uuid4()

    check_role = require_role("admin")

    with patch("app.auth.dependencies.get_current_user", return_value=user):
        with pytest.raises(HTTPException) as exc_info:
            await check_role(current_user=user)
    assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Plan 02-03: HTTP endpoint-тесты (интеграционные — требуют живой БД + Redis).
# Помечены @pytest.mark.integration (project convention: tests requiring Docker
# infrastructure); исключаются из CI `-m "not integration"`, запускаются в Docker.
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_register_success(client: AsyncClient) -> None:
    """POST /auth/register с валидными данными → 201 + access_token + HttpOnly refresh-cookie.

    AUTH-01: регистрация нового пользователя с уникальным email и сильным паролем.
    """
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.auth.models import User
    from app.core.config import settings

    email = "reg_success_0203@example.com"
    try:
        resp = await client.post(
            "/auth/register", json={"email": email, "password": "Str0ng!Passw0rd"}
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        set_cookie = resp.headers.get("set-cookie", "")
        assert "refresh_token=" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "Path=/auth" in set_cookie
    finally:
        engine = create_async_engine(settings.database_url)
        async with AsyncSession(engine) as session:
            await session.execute(delete(User).where(User.email == email))
            await session.commit()
        await engine.dispose()


@pytest.mark.integration
async def test_register_duplicate_email(client: AsyncClient, test_user: object) -> None:
    """POST /auth/register с уже существующим email → 409.

    AUTH-01: уникальность email гарантируется на уровне БД и сервиса.
    """
    resp = await client.post(
        "/auth/register",
        json={"email": test_user.email, "password": "Str0ng!Passw0rd"},  # type: ignore[attr-defined]
    )
    assert resp.status_code == 409


@pytest.mark.integration
async def test_register_weak_password(client: AsyncClient) -> None:
    """POST /auth/register со слабым паролем → 422 (Pydantic до записи в БД).

    AUTH-01 + D-04: политика пароля валидируется Pydantic-схемой.
    """
    resp = await client.post(
        "/auth/register", json={"email": "weakpw_0203@example.com", "password": "short"}
    )
    assert resp.status_code == 422


@pytest.mark.integration
async def test_login_success(client: AsyncClient, test_user: object) -> None:
    """POST /auth/login верные creds → 200 + access_token + HttpOnly refresh-cookie на /auth.

    AUTH-02: вход с JWT access 15 мин (HS256) + refresh в HttpOnly cookie.
    """
    resp = await client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "TestPassword1!"},  # type: ignore[attr-defined]
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "Path=/auth" in set_cookie


@pytest.mark.integration
async def test_login_wrong_password(client: AsyncClient, test_user: object) -> None:
    """POST /auth/login неверный пароль → 401 'Invalid credentials' (anti-enumeration).

    AUTH-02: одно сообщение для несуществующего email и неверного пароля.
    """
    resp = await client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "WrongPass1!"},  # type: ignore[attr-defined]
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials"


@pytest.mark.integration
async def test_logout_revokes_token(auth_client: AsyncClient) -> None:
    """POST /auth/logout пишет jti в Redis и чистит refresh-cookie; повторный запрос → 401.

    AUTH-03 (D-08): jti с TTL = остаток жизни токена; тот же токен после logout → 401 revoked.
    """
    logout = await auth_client.post("/auth/logout")
    assert logout.status_code == 200, logout.text
    set_cookie = logout.headers.get("set-cookie", "")
    assert "refresh_token=" in set_cookie  # delete_cookie выставляет истёкшую cookie
    revoked = await auth_client.get("/users/me")
    assert revoked.status_code == 401
    assert "revoked" in revoked.json()["detail"].lower()


@pytest.mark.integration
async def test_refresh_token(client: AsyncClient, test_user: object) -> None:
    """POST /auth/refresh с refresh-cookie из login → 200 + новый access_token.

    AUTH-04 (D-07): обновление access-токена без повторного логина.
    """
    login = await client.post(
        "/auth/login",
        json={"email": test_user.email, "password": "TestPassword1!"},  # type: ignore[attr-defined]
    )
    assert login.status_code == 200, login.text
    resp = await client.post("/auth/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.integration
async def test_rbac_db_layer(
    auth_client: AsyncClient, test_user: object, test_admin_user: object
) -> None:
    """user-токен на чужой /users/{id} → 404 (DB-layer RBAC, anti-enumeration); свой id → 200.

    AUTH-05 (D-12 уровень 2): owner-scoped get_user_for_principal → None для чужого ресурса → 404.
    """
    other = await auth_client.get(f"/users/{test_admin_user.id}")  # type: ignore[attr-defined]
    assert other.status_code == 404
    assert test_admin_user.email not in other.text  # type: ignore[attr-defined]
    own = await auth_client.get(f"/users/{test_user.id}")  # type: ignore[attr-defined]
    assert own.status_code == 200
    assert own.json()["email"] == test_user.email  # type: ignore[attr-defined]


@pytest.mark.integration
async def test_get_me(auth_client: AsyncClient, client: AsyncClient, test_user: object) -> None:
    """GET /users/me → 200 + профиль без password_hash; без Authorization → 401.

    AUTH-06 (D-13): просмотр профиля — id, email, role, is_active, created_at.
    """
    no_auth = await client.get("/users/me")
    assert no_auth.status_code == 401
    resp = await auth_client.get("/users/me")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email"] == test_user.email  # type: ignore[attr-defined]
    assert data["role"] == "user"
    assert data["is_active"] is True
    assert "password_hash" not in data


@pytest.mark.integration
async def test_change_password_wrong_current(auth_client: AsyncClient) -> None:
    """POST /users/me/password с неверным current_password → 400; новый хеш не пишется.

    AUTH-07 (D-05): верификация текущего пароля до записи нового.
    """
    resp = await auth_client.post(
        "/users/me/password",
        json={"current_password": "WrongCurrent1!", "new_password": "NewStr0ng!Pass1"},
    )
    assert resp.status_code == 400
    assert "incorrect" in resp.json()["detail"].lower()
