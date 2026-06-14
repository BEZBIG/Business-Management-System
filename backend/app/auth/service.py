"""Бизнес-логика домена аутентификации: регистрация, вход, смена пароля, seed admin.

Все функции принимают AsyncSession и не коммитят — commit делает get_async_session/lifespan.
RBAC уровень 2 (D-12): get_user_for_principal реализует owner-scoped DB-query фильтр.
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.security import password_hasher
from app.core.config import settings

logger = structlog.get_logger(__name__)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Ищет пользователя по email. Возвращает User или None."""
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, email: str, password: str) -> User:
    """Регистрирует нового пользователя с ролью USER (D-10).

    Хеширует пароль через Argon2id-синглтон. flush() обеспечивает id до commit.
    Проверку уникальности email делает вызывающий роутер (409).
    """
    hashed = password_hasher.hash(password)
    user = User(
        email=email,
        password_hash=hashed,
        role=UserRole.USER,  # роль всегда назначается сервером (D-10, T-02-08)
    )
    session.add(user)
    await session.flush()  # получить user.id до commit
    logger.info("user_created", email=email)
    return user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User | None:
    """Аутентифицирует пользователя. Единый None при любой ошибке (anti-enumeration, T-02-07).

    Не раскрывает, существует ли пользователь с таким email.
    """
    user = await get_user_by_email(session, email)
    if user is None:
        return None
    if not password_hasher.verify(password, user.password_hash):
        return None
    return user


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> bool:
    """Меняет пароль пользователя после верификации текущего (D-05).

    Возвращает False при несовпадении current_password; хеш не пишется.
    Возвращает True при успешной смене.
    """
    if not password_hasher.verify(current_password, user.password_hash):
        logger.warning("password_change_wrong_current", user_id=str(user.id))
        return False
    user.password_hash = password_hasher.hash(new_password)
    logger.info("password_changed", user_id=str(user.id))
    return True


async def seed_first_superuser(session: AsyncSession) -> None:
    """Идемпотентно создаёт первого admin из env-переменных (D-11).

    Не создаёт дубликат при существующем email. Не вызывается, если email пустой.
    """
    if not settings.first_superuser_email:
        return
    existing = await get_user_by_email(session, settings.first_superuser_email)
    if existing:
        logger.debug("seed_superuser_already_exists", email=settings.first_superuser_email)
        return
    hashed = password_hasher.hash(settings.first_superuser_password)
    admin = User(
        email=settings.first_superuser_email,
        password_hash=hashed,
        role=UserRole.ADMIN,
    )
    session.add(admin)
    logger.info("seed_superuser_created", email=settings.first_superuser_email)


async def get_user_for_principal(
    session: AsyncSession,
    target_user_id: object,
    principal: User,
) -> User | None:
    """DB-query-level RBAC: owner-scoped фильтр (D-12 уровень 2, T-02-22).

    - admin → возвращает любую строку (полный доступ).
    - user/manager → возвращает строку ТОЛЬКО если target_user_id == principal.id,
      иначе None (анти-энумерация: вызывающий отдаёт 404, не 403).

    None = нет доступа; вызывающий отдаёт 404 (не 403), чтобы не раскрывать
    существование чужого ресурса (anti-enumeration, T-02-22).
    """
    if principal.role == UserRole.ADMIN:
        # admin видит всех пользователей
        return await session.get(User, target_user_id)

    # user/manager — только собственная строка
    if str(target_user_id) == str(principal.id):
        return await session.get(User, target_user_id)

    # чужой ресурс — отказ (None → 404 у вызывающего)
    return None
