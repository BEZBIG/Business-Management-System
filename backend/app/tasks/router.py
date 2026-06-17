"""HTTP-слой домена задач: CRUD задач, комментарии, RBAC через team-membership.

Тонкие обработчики — вся логика в service.py.
Роутер вложен в team-контекст: /teams/{team_id}/tasks (D-05).
RBAC: get_team_membership (404 для не-членов) + require_task_editor (403).
Монтаж в main.py — будет добавлен в Plan 05.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db.session import get_async_session
from app.tasks.dependencies import get_task_or_404, require_task_editor
from app.tasks.models import Task
from app.tasks.schemas import (
    TaskCommentCreate,
    TaskCommentResponse,
    TaskCreate,
    TaskResponse,
    TaskUpdate,
)
from app.tasks.service import (
    add_comment,
    create_task,
    list_team_tasks,
    soft_delete_task,
    update_task,
)
from app.teams.dependencies import get_team_membership
from app.teams.models import TeamMember, TeamRole

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/teams/{team_id}/tasks", tags=["tasks"])


def _to_task_response(task: Task) -> TaskResponse:
    """Строит TaskResponse из ORM-объекта Task. status возвращается как str (.value)."""
    return TaskResponse(
        id=task.id,
        team_id=task.team_id,
        creator_id=task.creator_id,
        assignee_id=task.assignee_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        deadline=task.deadline,
        is_deleted=task.is_deleted,
        comments=[
            TaskCommentResponse(
                id=c.id,
                author_id=c.author_id,
                body=c.body,
                created_at=c.created_at,
            )
            for c in task.comments
        ],
        created_at=task.created_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task_endpoint(
    team_id: uuid.UUID,
    data: TaskCreate,
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TaskResponse:
    """Создаёт задачу в команде. Любой член команды может создавать задачи (D-05).

    assignee_id должен быть членом той же команды (проверяется в service) → 422 при нарушении.
    """
    task = await create_task(
        session,
        team_id=team_id,
        creator_id=current_user.id,
        title=data.title,
        description=data.description,
        assignee_id=data.assignee_id,
        deadline=data.deadline,
    )
    logger.info("tasks_create", task_id=str(task.id), team_id=str(team_id))
    return _to_task_response(task)


@router.get("")
async def list_tasks_endpoint(
    team_id: uuid.UUID,
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> list[TaskResponse]:
    """Возвращает список активных задач команды (is_deleted=False — D-09).

    Не-член команды получает 404 (анти-энумерация, через get_team_membership).
    """
    tasks = await list_team_tasks(session, team_id)
    return [_to_task_response(t) for t in tasks]


@router.get("/{task_id}")
async def get_task_endpoint(
    team_id: uuid.UUID,
    task: Task = Depends(get_task_or_404),  # noqa: B008
) -> TaskResponse:
    """Возвращает задачу с вложенными комментариями (D-11).

    Soft-deleted задача → 404 (D-09); чужая команда → 404 (IDOR-защита, T-03-10).
    """
    return _to_task_response(task)


@router.patch("/{task_id}")
async def update_task_endpoint(
    team_id: uuid.UUID,
    data: TaskUpdate,
    task: Task = Depends(require_task_editor),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TaskResponse:
    """Обновляет задачу. Только assignee/creator/manager/owner (D-08, require_task_editor).

    Смена status проходит через validate_status_transition → 422 при нарушении (D-07).
    Concurrent-safe UPDATE по статусу → 409 при конкурентном изменении.
    """
    updated = await update_task(
        session,
        task=task,
        title=data.title,
        description=data.description,
        assignee_id=data.assignee_id,
        deadline=data.deadline,
        status=data.status,
    )
    logger.info("tasks_update", task_id=str(task.id), team_id=str(team_id))
    return _to_task_response(updated)


@router.delete("/{task_id}")
async def delete_task_endpoint(
    team_id: uuid.UUID,
    task: Task = Depends(get_task_or_404),  # noqa: B008
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> dict[str, str]:
    """Soft-delete задачи (D-09). Разрешено creator + manager/owner (D-08).

    После удаления задача не видна в списке и detail → 404 (T-03-13).
    """
    is_creator = task.creator_id == current_user.id
    is_privileged = membership.role in (TeamRole.OWNER, TeamRole.MANAGER)

    if not (is_creator or is_privileged):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this task",
        )

    await soft_delete_task(session, task)
    logger.info("tasks_delete", task_id=str(task.id), team_id=str(team_id))
    return {"detail": "Task deleted"}


@router.post("/{task_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment_endpoint(
    team_id: uuid.UUID,
    task_id: uuid.UUID,
    data: TaskCommentCreate,
    task: Task = Depends(get_task_or_404),  # noqa: B008
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> TaskCommentResponse:
    """Добавляет комментарий к задаче (D-11). Любой член команды может комментировать."""
    comment = await add_comment(session, task_id=task.id, author_id=current_user.id, body=data.body)
    logger.info("tasks_comment_add", task_id=str(task.id), author_id=str(current_user.id))
    return TaskCommentResponse(
        id=comment.id,
        author_id=comment.author_id,
        body=comment.body,
        created_at=comment.created_at,
    )
