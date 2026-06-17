"""Бизнес-логика домена задач: CRUD, state machine статусов, soft-delete, assignee-валидация.

Все функции принимают AsyncSession и не коммитят — commit делает get_async_session.
flush() используется для получения id до commit.

State machine (D-07):
  OPEN → IN_PROGRESS → DONE → IN_PROGRESS
  Прямой переход OPEN → DONE запрещён → 422.

Assignee (D-05): должен быть членом команды задачи, иначе 422.
Soft-delete (D-09): is_deleted=True + archived_at=now(UTC); hard-delete отсутствует.
selectinload(Task.comments): обязателен во всех detail-запросах (Pitfall 1).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.tasks.models import Task, TaskComment, TaskStatus
from app.teams.service import get_team_member

logger = structlog.get_logger(__name__)

# D-07: допустимые переходы статусов. open→done отсутствует намеренно.
ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.OPEN: {TaskStatus.IN_PROGRESS},
    TaskStatus.IN_PROGRESS: {TaskStatus.OPEN, TaskStatus.DONE},
    TaskStatus.DONE: {TaskStatus.IN_PROGRESS},
}


def validate_status_transition(current: TaskStatus, requested: TaskStatus) -> None:
    """Проверяет допустимость перехода статуса. No-op если статус не изменился (D-07).

    Недопустимый переход (в т.ч. open→done) → HTTPException 422.
    """
    if requested == current:
        return
    if requested not in ALLOWED_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Status transition {current.value} → {requested.value} is not allowed",
        )


async def validate_assignee_membership(
    session: AsyncSession, team_id: uuid.UUID, assignee_id: uuid.UUID
) -> None:
    """Проверяет, что assignee является членом команды задачи (D-05).

    Нечлен команды → HTTPException 422.
    """
    member = await get_team_member(session, team_id, assignee_id)
    if member is None:
        raise HTTPException(
            status_code=422,
            detail="Assignee must be a member of the task's team",
        )


async def create_task(
    session: AsyncSession,
    team_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: str,
    description: str | None = None,
    assignee_id: uuid.UUID | None = None,
    deadline: datetime | None = None,
) -> Task:
    """Создаёт задачу в команде. assignee проверяется на членство (D-05).

    deadline должен быть timezone-aware или None (D-10).
    flush() обеспечивает task.id до commit.
    """
    if assignee_id is not None:
        await validate_assignee_membership(session, team_id, assignee_id)

    task = Task(
        team_id=team_id,
        creator_id=creator_id,
        title=title,
        description=description,
        assignee_id=assignee_id,
        deadline=deadline,
        status=TaskStatus.OPEN,
    )
    session.add(task)
    await session.flush()
    logger.info("task_created", task_id=str(task.id), team_id=str(team_id))
    return task


async def update_task(
    session: AsyncSession,
    task: Task,
    title: str | None = None,
    description: str | None = None,
    assignee_id: uuid.UUID | None = None,
    deadline: datetime | None = None,
    status: str | None = None,
) -> Task:
    """Обновляет поля задачи. Смена статуса проходит через validate_status_transition (D-07).

    При concurrent UPDATE по статусу: проверяет rowcount → 409 при конфликте (Pitfall 6).
    """
    if title is not None:
        task.title = title
    if description is not None:
        task.description = description
    if assignee_id is not None:
        await validate_assignee_membership(session, task.team_id, assignee_id)
        task.assignee_id = assignee_id
    if deadline is not None:
        task.deadline = deadline

    if status is not None:
        requested = TaskStatus(status)
        validate_status_transition(task.status, requested)
        # Concurrent-safe UPDATE: WHERE status=:current → проверяем rowcount (Pitfall 6)
        cursor: CursorResult[tuple[()]] = await session.execute(  # type: ignore[assignment]
            update(Task)
            .where(Task.id == task.id, Task.status == task.status)
            .values(status=requested)
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=409,
                detail="Task status was changed concurrently, please retry",
            )
        task.status = requested

    await session.flush()
    logger.info("task_updated", task_id=str(task.id))
    return task


async def soft_delete_task(session: AsyncSession, task: Task) -> None:
    """Помечает задачу удалённой (D-09). Hard-delete отсутствует.

    is_deleted=True, archived_at=now(UTC). Комментарии и оценки сохраняются.
    """
    task.is_deleted = True
    task.archived_at = datetime.now(UTC)
    await session.flush()
    logger.info("task_soft_deleted", task_id=str(task.id))


async def get_task_detail(session: AsyncSession, task_id: uuid.UUID) -> Task | None:
    """Загружает задачу с вложенными комментариями через selectinload (Pitfall 1, D-11).

    Фильтрует удалённые задачи (is_deleted is False — D-09).
    Возвращает None если задача не найдена или помечена удалённой.
    """
    result = await session.execute(
        select(Task)
        .where(Task.id == task_id, Task.is_deleted.is_(False))
        .options(selectinload(Task.comments))
    )
    return result.scalar_one_or_none()


async def list_team_tasks(session: AsyncSession, team_id: uuid.UUID) -> list[Task]:
    """Возвращает список активных задач команды (фильтр is_deleted is False — D-09)."""
    result = await session.execute(
        select(Task)
        .where(Task.team_id == team_id, Task.is_deleted.is_(False))
        .options(selectinload(Task.comments))
    )
    return list(result.scalars().all())


async def add_comment(
    session: AsyncSession,
    task_id: uuid.UUID,
    author_id: uuid.UUID,
    body: str,
) -> TaskComment:
    """Добавляет комментарий к задаче (D-11). Любой член команды может комментировать."""
    comment = TaskComment(
        task_id=task_id,
        author_id=author_id,
        body=body,
    )
    session.add(comment)
    await session.flush()
    logger.info("comment_added", task_id=str(task_id), author_id=str(author_id))
    return comment
