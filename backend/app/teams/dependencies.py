"""FastAPI-зависимости для домена команд: проверка членства и RBAC.

get_team_membership: возвращает TeamMember или 404 (анти-энумерация — не 403).
require_team_role: параметрическая фабрика зависимостей — 403 только при недостаточной роли.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db.session import get_async_session
from app.teams.models import TeamMember, TeamRole


async def get_team_membership(
    team_id: uuid.UUID,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TeamMember:
    """Проверяет членство текущего пользователя в команде.

    Отсутствие записи → 404 «Team not found» (анти-энумерация: не раскрываем
    существование команды не-членам). 403 выдаёт только require_team_role.
    """
    result = await session.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id == current_user.id,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return membership


def require_team_role(*roles: TeamRole):  # type: ignore[no-untyped-def]
    """Фабрика зависимостей командного RBAC.

    Использование:
        dependencies=[Depends(require_team_role(TeamRole.OWNER, TeamRole.MANAGER))]

    Возвращает 403 при недостаточной роли; 404 уже обработан get_team_membership.
    """

    async def check_team_role(
        membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    ) -> TeamMember:
        """Проверяет, что роль участника входит в разрешённый список."""
        if membership.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient team role")
        return membership

    return check_team_role
