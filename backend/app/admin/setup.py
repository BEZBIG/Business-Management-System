"""SQLAdmin панель: AdminAuthBackend на itsdangerous session-cookie + UserAdmin view.

Монтируется через setup_admin(app, engine) в main.py (D-15).
SessionMiddleware автоматически добавляется sqladmin в sub-app /admin — вручную не добавлять.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.requests import Request

from app.auth.models import User, UserRole
from app.auth.security import password_hasher
from app.auth.service import get_user_by_email
from app.core.config import settings
from app.db.engine import async_session_factory

logger = structlog.get_logger(__name__)


class AdminAuthBackend(AuthenticationBackend):
    """Кастомный backend аутентификации SQLAdmin (D-14).

    Переиспользует password_hasher и таблицу User — единая точка истины по кредам.
    Требует role == ADMIN; неаутентифицированные и не-admin отклоняются.
    """

    async def login(self, request: Request) -> bool:
        """Верифицирует admin-кредения из login-формы SQLAdmin.

        Поле логина в форме SQLAdmin называется 'username' (не 'email').
        """
        form = await request.form()
        email = str(form.get("username", ""))
        password = str(form.get("password", ""))

        async with async_session_factory() as session:
            user = await get_user_by_email(session, email)

        if user is None or not user.is_active:
            logger.warning("admin_login_failed_user_not_found", email=email)
            return False

        if not password_hasher.verify(password, user.password_hash):
            logger.warning("admin_login_failed_wrong_password", email=email)
            return False

        if user.role != UserRole.ADMIN:
            logger.warning("admin_login_failed_not_admin", email=email, role=user.role.value)
            return False

        # itsdangerous подписывает cookie автоматически через SessionMiddleware sub-app SQLAdmin
        request.session.update({"user_email": user.email, "role": user.role.value})
        logger.info("admin_login_success", email=email)
        return True

    async def logout(self, request: Request) -> bool:
        """Очищает admin-сессию."""
        request.session.clear()
        logger.info("admin_logout", email=request.session.get("user_email", "unknown"))
        return True

    async def authenticate(self, request: Request) -> bool:
        """Проверяет наличие admin-сессии на каждый запрос /admin/*."""
        return request.session.get("role") == "admin"


class UserAdmin(ModelView, model=User):
    """Admin-представление модели User.

    column_list — только скалярные поля (D-15, Pitfall 1 MissingGreenlet):
    никаких relationships во избежание N+1 и MissingGreenlet в async-контексте.
    """

    name = "User"
    name_plural = "Users"
    # ТОЛЬКО скалярные поля — guard от MissingGreenlet (D-15, STATE Фазы 1)
    column_list = [User.id, User.email, User.role, User.is_active, User.created_at]
    # Мягкое удаление через is_active — прямое DELETE из UI запрещено
    can_delete = False


def setup_admin(app: FastAPI, engine: AsyncEngine) -> None:
    """Монтирует SQLAdmin панель с кастомным AuthenticationBackend (D-15).

    Передаёт тот же async engine из app.db.engine — не создавать новый.
    SessionMiddleware добавляется sqladmin в свой sub-app автоматически —
    НЕ добавлять вручную к родительскому app (создаст дубль, Pitfall 4 RESOLVED).
    """
    auth_backend = AdminAuthBackend(secret_key=settings.admin_session_secret)
    admin = Admin(app=app, engine=engine, authentication_backend=auth_backend)
    admin.add_view(UserAdmin)
