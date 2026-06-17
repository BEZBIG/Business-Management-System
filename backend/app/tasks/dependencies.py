"""FastAPI-зависимости для домена задач: получение задачи и проверка прав редактирования.

get_task_or_404: загружает задачу с защитой от IDOR (D-05, T-03-10).
    Зависит от get_team_membership — не-члены команды получают 404 до доступа к задаче.

require_task_editor: проверяет права редактирования (D-08, T-03-14).
    Разрешено: assignee, creator, manager, owner; остальные → 403.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db.session import get_async_session
from app.tasks.models import Task
from app.tasks.service import get_task_detail
from app.teams.dependencies import get_team_membership
from app.teams.models import TeamMember, TeamRole


async def get_task_or_404(
    team_id: uuid.UUID,
    task_id: uuid.UUID,
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> Task:
    """Загружает задачу команды или возвращает 404 (анти-IDOR, T-03-10).

    Порядок проверок:
    1. get_team_membership (встроен через Depends) — не-член → 404 «Team not found»
       (до проверки задачи, чтобы не раскрывать существование задач чужой команды).
    2. get_task_detail — задача не найдена или is_deleted → 404.
    3. Задача принадлежит другой команде (team_id в path не совпадает) → 404.
    """
    task = await get_task_detail(session, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.team_id != team_id:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def require_task_editor(
    task: Task = Depends(get_task_or_404),  # noqa: B008
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> Task:
    """Проверяет права на редактирование задачи (D-08, T-03-14).

    Разрешено, если текущий пользователь:
    - assignee задачи, или
    - creator задачи, или
    - manager/owner команды.

    Иначе → 403 «Not authorized to edit this task».
    """
    is_assignee = task.assignee_id is not None and task.assignee_id == current_user.id
    is_creator = task.creator_id == current_user.id
    is_privileged = membership.role in (TeamRole.OWNER, TeamRole.MANAGER)

    if not (is_assignee or is_creator or is_privileged):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to edit this task",
        )
    return task
