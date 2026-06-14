"""FastAPI-зависимости аутентификации и авторизации.

get_current_user: проверяет подпись JWT, exp, type, jti-ревокацию, is_active (D-08).
require_role: фабрика route-level RBAC зависимостей (D-12 уровень 1).
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.security import decode_access_token
from app.core.redis_client import redis_client
from app.db.session import get_async_session

# auto_error=False — позволяет вернуть собственный 401 вместо дефолтного Starlette
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> User:
    """Извлекает и верифицирует текущего пользователя из Bearer-токена.

    Проверяет последовательно:
    1. Наличие Authorization заголовка → 401
    2. Подпись JWT и exp → 401 "Token expired" / "Invalid token"
    3. type == "access" → 401 "Invalid token type"
    4. jti в Redis revocation-set → 401 "Token revoked" (D-08, T-02-05)
    5. Пользователь существует и is_active → 401
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = credentials.credentials
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    jti = payload.get("jti", "")
    if bool(await redis_client.exists(f"jti:{jti}")):
        raise HTTPException(status_code=401, detail="Token revoked")

    user_id = payload.get("sub")
    user: User | None = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


def require_role(*roles: str):  # type: ignore[no-untyped-def]
    """Фабрика route-level RBAC зависимостей (D-12 уровень 1).

    Использование:
        @router.get("/admin", dependencies=[Depends(require_role("admin"))])
        async def admin_handler(user: User = Depends(require_role("admin"))) -> ...:
            ...

    Отклоняет принципала с недостаточной ролью → 403 "Insufficient permissions".
    """

    async def check_role(
        current_user: User = Depends(get_current_user),  # noqa: B008
    ) -> User:
        if current_user.role.value not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return check_role
