"""HTTP-слой аутентификации: /auth/* (register/login/refresh/logout) и /users/* (профиль, RBAC).

Тонкие обработчики: вызывают service.py, ставят/чистят refresh-cookie (D-07, HttpOnly+SameSite,
scoped на /auth) и отзывают access-токен через Redis на logout (D-08). Два роутера в одном
модуле (W2): router (/auth/*) и users_router (/users/*) — оба экспортируются.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import bearer_scheme, get_current_user
from app.auth.models import User
from app.auth.schemas import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RegisterRequest,
    UserMeResponse,
    UserUpdateRequest,
)
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)
from app.auth.service import (
    authenticate_user,
    change_password,
    create_user,
    get_user_by_email,
    get_user_for_principal,
)
from app.core.config import settings
from app.core.redis_client import redis_client
from app.db.session import get_async_session

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])

REFRESH_COOKIE_NAME = "refresh_token"  # noqa: S105
REFRESH_COOKIE_PATH = "/auth"


def _to_me_response(user: User) -> UserMeResponse:
    """Строит UserMeResponse из ORM-User без password_hash (T-02-09).

    role.value (str) передаётся явно — UserRole(enum.Enum) не str-enum, поэтому
    model_validate не сериализует его в строковое поле role.
    """
    return UserMeResponse(
        id=user.id,
        email=user.email,
        role=user.role.value,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _set_refresh_cookie(response: JSONResponse, token: str) -> None:
    """Ставит refresh-токен в HttpOnly+SameSite cookie, scoped на /auth (D-07, T-02-11/12)."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=(settings.environment == "prod"),
        samesite="lax",
        max_age=settings.refresh_token_ttl,
        path=REFRESH_COOKIE_PATH,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> JSONResponse:
    """Регистрирует пользователя → 201 + access token + refresh-cookie; дубликат email → 409."""
    if await get_user_by_email(session, data.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = await create_user(session, data.email, data.password)
    access = create_access_token(sub=str(user.id), role=user.role.value)
    refresh = create_refresh_token(sub=str(user.id))
    logger.info("auth_register", user_id=str(user.id))
    response = JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=LoginResponse(access_token=access).model_dump(),
    )
    _set_refresh_cookie(response, refresh)
    return response


@router.post("/login")
async def login(
    data: LoginRequest,
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> JSONResponse:
    """Вход по кредам → access token + refresh-cookie; ошибка → 401 'Invalid credentials'.

    Единое сообщение для неверного email И пароля — anti-enumeration (T-02-14).
    """
    user = await authenticate_user(session, data.email, data.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = create_access_token(sub=str(user.id), role=user.role.value)
    refresh = create_refresh_token(sub=str(user.id))
    logger.info("auth_login", user_id=str(user.id))
    response = JSONResponse(content=LoginResponse(access_token=access).model_dump())
    _set_refresh_cookie(response, refresh)
    return response


@router.post("/refresh")
async def refresh(
    refresh_token: str | None = Cookie(default=None),
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> LoginResponse:
    """Выдаёт новый access token по refresh-cookie без повторного логина (AUTH-04, D-07)."""
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token"
        )
    try:
        payload = decode_refresh_token(refresh_token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from exc
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
    user = await session.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )
    access = create_access_token(sub=str(user.id), role=user.role.value)
    return LoginResponse(access_token=access)


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> JSONResponse:
    """Отзывает access-токен (jti → Redis с TTL остатка) и чистит refresh-cookie (AUTH-03, D-08)."""
    if credentials is None:  # недостижимо — get_current_user уже потребовал токен
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = decode_access_token(credentials.credentials)
    jti = str(payload.get("jti", ""))
    exp_claim = payload.get("exp", 0)
    exp = int(exp_claim) if isinstance(exp_claim, (int, float)) else 0
    remaining = exp - int(datetime.now(UTC).timestamp())
    if jti and remaining > 0:
        await redis_client.set(f"jti:{jti}", "1", ex=remaining)
    response = JSONResponse(content={"detail": "Logged out"})
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    logger.info("auth_logout", user_id=str(current_user.id))
    return response


@users_router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> UserMeResponse:
    """Возвращает профиль текущего пользователя (AUTH-06, D-13)."""
    return _to_me_response(current_user)


@users_router.patch("/me")
async def update_me(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> UserMeResponse:
    """Обновляет профиль (email); role/is_active клиентом не меняются (D-10/D-13)."""
    if data.email is not None:
        current_user.email = data.email
    await session.flush()
    return _to_me_response(current_user)


@users_router.post("/me/password")
async def change_my_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> dict[str, str]:
    """Меняет пароль после верификации текущего; неверный current → 400 (AUTH-07, D-05)."""
    ok = await change_password(session, current_user, data.current_password, data.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    logger.info("auth_password_changed", user_id=str(current_user.id))
    return {"detail": "Password changed"}


@users_router.get("/{user_id}")
async def get_user_by_id(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> UserMeResponse:
    """Owner-scoped чтение профиля (AUTH-05, D-12 ур.2): чужой id для user-роли → 404.

    get_user_for_principal возвращает None для чужого ресурса → 404 (не 403) —
    anti-enumeration существования (T-02-23).
    """
    target = await get_user_for_principal(session, user_id, current_user)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _to_me_response(target)
