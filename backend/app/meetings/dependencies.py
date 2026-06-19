"""FastAPI-зависимости для домена встреч: загрузка встречи и проверка прав владельца.

get_meeting_or_404: загружает встречу с защитой от IDOR (D-10).
    Зависит от get_team_membership — не-члены команды получают 404 до доступа к встрече.

require_meeting_owner: проверяет право отмены встречи (D-03).
    Разрешено только creator; остальные участники → 403.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db.session import get_async_session
from app.meetings.models import Meeting
from app.meetings.service import get_meeting_detail
from app.teams.dependencies import get_team_membership
from app.teams.models import TeamMember


async def get_meeting_or_404(
    team_id: uuid.UUID,
    meeting_id: uuid.UUID,
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> Meeting:
    """Загружает активную встречу команды или возвращает 404 (анти-IDOR, D-10).

    Порядок проверок:
    1. get_team_membership (через Depends) — не-член → 404 «Team not found»
       (до проверки встречи, чтобы не раскрывать существование встреч чужой команды).
    2. get_meeting_detail — встреча не найдена или отменена → 404.
    3. Встреча принадлежит другой команде → 404 (cross-team IDOR).
    """
    meeting = await get_meeting_detail(session, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if meeting.team_id != team_id:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return meeting


async def require_meeting_owner(
    meeting: Meeting = Depends(get_meeting_or_404),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> Meeting:
    """Проверяет, что текущий пользователь является создателем встречи (D-03).

    Только creator может отменять встречу.
    Участник, не являющийся creator → 403.
    """
    if meeting.creator_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Only meeting owner can perform this action",
        )
    return meeting
