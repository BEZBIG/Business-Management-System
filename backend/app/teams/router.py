"""HTTP-слой домена команд: CRUD команды, вступление по invite-коду, управление составом.

Тонкие обработчики — вся логика в service.py.
RBAC: get_team_membership (404 для не-членов) + require_team_role (403 при недостаточной роли).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db.session import get_async_session
from app.teams.dependencies import get_team_membership, require_team_role
from app.teams.models import TeamMember, TeamRole
from app.teams.schemas import (
    AddMemberRequest,
    JoinTeamRequest,
    SetRoleRequest,
    TeamCreate,
    TeamMemberResponse,
    TeamResponse,
)
from app.teams.service import (
    add_member,
    create_team,
    get_team_by_id,
    join_team,
    remove_member,
    set_member_role,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/teams", tags=["teams"])


def _to_team_response(team: object) -> TeamResponse:
    """Строит TeamResponse из ORM-объекта Team."""
    return TeamResponse.model_validate(team)


def _to_member_response(member: TeamMember) -> TeamMemberResponse:
    """Строит TeamMemberResponse из ORM-объекта TeamMember. role отдаётся как str (.value)."""
    return TeamMemberResponse(
        team_id=member.team_id,
        user_id=member.user_id,
        role=member.role.value,
        created_at=member.created_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_team_endpoint(
    data: TeamCreate,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TeamResponse:
    """Создаёт команду и назначает создателя owner. Возвращает 201 + TeamResponse с invite_code."""
    team = await create_team(session, data.name, current_user.id)
    logger.info("teams_create", team_id=str(team.id), creator_id=str(current_user.id))
    return _to_team_response(team)


@router.post("/{team_id}/join")
async def join_team_endpoint(
    team_id: uuid.UUID,
    data: JoinTeamRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TeamMemberResponse:
    """Вступление в команду по invite-коду. Неверный код → 400. Повторный join → 200 без дубля."""
    member = await join_team(session, data.code, current_user.id)
    if member is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite code")
    # Проверяем, что присоединение к нужной команде (code матчит team_id)
    if member.team_id != team_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invite code")
    logger.info("teams_join", team_id=str(team_id), user_id=str(current_user.id))
    return _to_member_response(member)


@router.get("/{team_id}")
async def get_team_endpoint(
    team_id: uuid.UUID,
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TeamResponse:
    """Возвращает данные команды. Не-член получает 404 (анти-энумерация)."""
    team = await get_team_by_id(session, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return _to_team_response(team)


@router.post("/{team_id}/members")
async def add_member_endpoint(
    team_id: uuid.UUID,
    data: AddMemberRequest,
    membership: TeamMember = Depends(require_team_role(TeamRole.OWNER, TeamRole.MANAGER)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TeamMemberResponse:
    """Добавляет участника в команду. Только owner/manager — 403 для member."""
    try:
        role = TeamRole(data.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role: {data.role}",
        ) from exc

    # Только owner может назначить роль OWNER
    if role == TeamRole.OWNER and membership.role != TeamRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only an owner can assign the owner role",
        )

    member = await add_member(session, team_id, data.user_id, role)
    logger.info(
        "teams_add_member",
        team_id=str(team_id),
        user_id=str(data.user_id),
        role=role.value,
    )
    return _to_member_response(member)


@router.delete("/{team_id}/members/{user_id}")
async def remove_member_endpoint(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    membership: TeamMember = Depends(require_team_role(TeamRole.OWNER, TeamRole.MANAGER)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> dict[str, str]:
    """Удаляет участника из команды. Только owner/manager — 403 для member."""
    try:
        removed = await remove_member(session, team_id, user_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    logger.info("teams_remove_member", team_id=str(team_id), user_id=str(user_id))
    return {"detail": "Member removed"}


@router.patch("/{team_id}/members/{user_id}/role")
async def set_role_endpoint(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    data: SetRoleRequest,
    membership: TeamMember = Depends(require_team_role(TeamRole.OWNER, TeamRole.MANAGER)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TeamMemberResponse:
    """Устанавливает командную роль участника. Только owner/manager — 403 для member.

    Повышение до OWNER возможно только для owner-а (D-03).
    """
    try:
        new_role = TeamRole(data.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid role: {data.role}",
        ) from exc

    try:
        member = await set_member_role(session, team_id, user_id, new_role, membership.role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc

    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    logger.info(
        "teams_set_role",
        team_id=str(team_id),
        user_id=str(user_id),
        new_role=new_role.value,
    )
    return _to_member_response(member)
