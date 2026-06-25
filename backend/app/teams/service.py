"""Бизнес-логика домена команд: создание, вступление, управление составом и ролями.

Все функции принимают AsyncSession и не коммитят — commit делает get_async_session.
flush() используется для получения id до commit.
"""

from __future__ import annotations

import secrets
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.teams.models import Team, TeamMember, TeamRole

logger = structlog.get_logger(__name__)


async def get_team_by_id(session: AsyncSession, team_id: uuid.UUID) -> Team | None:
    """Ищет команду по id. Возвращает Team или None."""
    result = await session.execute(select(Team).where(Team.id == team_id))
    return result.scalar_one_or_none()


async def get_team_by_invite_code(session: AsyncSession, invite_code: str) -> Team | None:
    """Ищет команду по invite-коду. Возвращает Team или None."""
    result = await session.execute(select(Team).where(Team.invite_code == invite_code))
    return result.scalar_one_or_none()


async def get_team_member(
    session: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID
) -> TeamMember | None:
    """Ищет запись членства (team_id, user_id). Возвращает TeamMember или None."""
    result = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_team(session: AsyncSession, name: str, creator_id: uuid.UUID) -> Team:
    """Создаёт команду и автоматически добавляет создателя как owner (D-01, D-04).

    invite_code генерируется через secrets.token_urlsafe(32) — 256 бит энтропии.
    """
    team = Team(
        name=name,
        invite_code=secrets.token_urlsafe(32),
    )
    session.add(team)
    await session.flush()  # получить team.id до commit

    owner_link = TeamMember(
        team_id=team.id,
        user_id=creator_id,
        role=TeamRole.OWNER,
    )
    session.add(owner_link)
    await session.flush()

    logger.info("team_created", team_id=str(team.id), creator_id=str(creator_id))
    return team


async def join_team(
    session: AsyncSession, invite_code: str, user_id: uuid.UUID
) -> TeamMember | None:
    """Вступление в команду по invite-коду (D-02, D-04).

    Идемпотентно: повторный join тем же пользователем возвращает существующее членство
    без создания дубля. Неверный код → None (вызывающий → 400/404).
    """
    team = await get_team_by_invite_code(session, invite_code)
    if team is None:
        return None

    # Идемпотентность: проверяем существующее членство
    existing = await get_team_member(session, team.id, user_id)
    if existing is not None:
        logger.info("team_join_idempotent", team_id=str(team.id), user_id=str(user_id))
        return existing

    member = TeamMember(
        team_id=team.id,
        user_id=user_id,
        role=TeamRole.MEMBER,
    )
    session.add(member)
    await session.flush()
    logger.info("team_joined", team_id=str(team.id), user_id=str(user_id))
    return member


async def add_member(
    session: AsyncSession,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    role: TeamRole = TeamRole.MEMBER,
) -> TeamMember:
    """Добавляет участника в команду с указанной ролью.

    Если участник уже состоит в команде, возвращает существующее членство.
    """
    existing = await get_team_member(session, team_id, user_id)
    if existing is not None:
        logger.info("add_member_idempotent", team_id=str(team_id), user_id=str(user_id))
        return existing

    member = TeamMember(
        team_id=team_id,
        user_id=user_id,
        role=role,
    )
    session.add(member)
    await session.flush()
    logger.info("member_added", team_id=str(team_id), user_id=str(user_id), role=role.value)
    return member


async def remove_member(session: AsyncSession, team_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Удаляет участника из команды (D-03, T-03-09).

    Запрещает удаление последнего owner команды — защита от обезглавливания.
    Возвращает True при успехе, бросает ValueError при попытке удалить последнего owner.
    """
    member = await get_team_member(session, team_id, user_id)
    if member is None:
        return False

    if member.role == TeamRole.OWNER:
        # Проверяем: остался ли ещё хотя бы один другой owner
        result = await session.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.role == TeamRole.OWNER,
                TeamMember.user_id != user_id,
            )
        )
        other_owner = result.scalar_one_or_none()
        if other_owner is None:
            raise ValueError("Cannot remove the last owner of a team")

    await session.delete(member)
    await session.flush()
    logger.info("member_removed", team_id=str(team_id), user_id=str(user_id))
    return True


async def set_member_role(
    session: AsyncSession,
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    new_role: TeamRole,
    requester_role: TeamRole,
) -> TeamMember | None:
    """Устанавливает командную роль участника (D-03, D-04).

    Только owner может назначить роль OWNER другому участнику.
    Manager может назначать только MANAGER/MEMBER.
    Возвращает обновлённый TeamMember или None если участник не найден.
    """
    member = await get_team_member(session, team_id, user_id)
    if member is None:
        return None

    # Только owner может выдать роль OWNER (защита от privilege escalation)
    if new_role == TeamRole.OWNER and requester_role != TeamRole.OWNER:
        raise ValueError("Only an owner can assign the owner role")

    member.role = new_role
    await session.flush()
    logger.info(
        "role_changed",
        team_id=str(team_id),
        user_id=str(user_id),
        new_role=new_role.value,
    )
    return member
