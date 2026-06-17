"""Бизнес-логика домена оценок: guards, upsert по (task_id, rater_id), on-the-fly AVG.

Все функции принимают AsyncSession и не коммитят — commit делает get_async_session.

Guards (D-13):
  - task.status != DONE → HTTPException 422
  - task.assignee_id is None → HTTPException 422 (нет исполнителя — некого оценивать)
  - rater_id == task.assignee_id → HTTPException 403 (самооценка запрещена)

Upsert (D-14): ON CONFLICT (task_id, rater_id) DO UPDATE — один рейтинг на пару,
повторная оценка обновляет score + updated_at (Pitfall 4: onupdate ORM-хук не срабатывает
при dialect-level INSERT, поэтому updated_at прописывается явно через sa.func.now()).

AVG (D-15): on-the-fly SQL AVG по строкам где ratee_id == user_id; None при отсутствии оценок.
Decimal → float через явный cast (A1).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
import structlog
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.ratings.models import Rating
from app.tasks.models import Task, TaskStatus

logger = structlog.get_logger(__name__)


def validate_rating_state(task: Task, rater_id: uuid.UUID) -> None:
    """Проверяет допустимость выставления оценки по задаче (D-13).

    Порядок проверок:
    1. task.status != DONE → 422 (оценивать можно только выполненные задачи)
    2. task.assignee_id is None → 422 (нет исполнителя — некого оценивать)
    3. rater_id == task.assignee_id → 403 (самооценка запрещена)
    """
    if task.status != TaskStatus.DONE:
        raise HTTPException(
            status_code=422,
            detail="Rating is only allowed for tasks with status 'done'",
        )
    if task.assignee_id is None:
        raise HTTPException(
            status_code=422,
            detail="Cannot rate a task without an assignee",
        )
    if task.assignee_id == rater_id:
        raise HTTPException(
            status_code=403,
            detail="Self-rating is not allowed",
        )


async def upsert_rating(
    session: AsyncSession,
    task_id: uuid.UUID,
    rater_id: uuid.UUID,
    ratee_id: uuid.UUID,
    score: int,
) -> Rating:
    """Создаёт или обновляет оценку через PostgreSQL ON CONFLICT DO UPDATE (D-14).

    Конфликт по UNIQUE(task_id, rater_id) — обновляет score и updated_at.
    updated_at задаётся явно через sa.func.now() — ORM onupdate не срабатывает
    при dialect-level INSERT (Pitfall 4).
    ratee_id = task.assignee_id (D-12).
    """
    stmt = (
        pg_insert(Rating)
        .values(
            task_id=task_id,
            rater_id=rater_id,
            ratee_id=ratee_id,
            score=score,
        )
        .on_conflict_do_update(
            index_elements=["task_id", "rater_id"],
            set_={
                "score": score,
                "updated_at": sa.func.now(),
            },
        )
        .returning(Rating)
    )
    result = await session.execute(stmt)
    await session.flush()
    rating = result.scalar_one()
    logger.info("rating_upserted", task_id=str(task_id), rater_id=str(rater_id), score=score)
    return rating


async def get_avg_rating_alltime(
    session: AsyncSession,
    ratee_id: uuid.UUID,
) -> tuple[float | None, int]:
    """Возвращает all-time среднюю оценку и количество оценок для исполнителя (RATE-02).

    Decimal → float (A1). None при отсутствии оценок — не 0.
    """
    result = await session.execute(
        select(func.avg(Rating.score), func.count(Rating.id)).where(
            Rating.ratee_id == ratee_id,
        )
    )
    row = result.one()
    raw_avg, count = row[0], row[1]
    return (float(raw_avg) if raw_avg is not None else None), int(count)


async def get_avg_rating_period(
    session: AsyncSession,
    ratee_id: uuid.UUID,
    from_: datetime,
    to_: datetime,
) -> tuple[float | None, int]:
    """Возвращает среднюю оценку за период [from_, to_] для исполнителя (RATE-03).

    Фильтр по created_at (D-15). Decimal → float (A1). None при отсутствии оценок.
    """
    result = await session.execute(
        select(func.avg(Rating.score), func.count(Rating.id)).where(
            Rating.ratee_id == ratee_id,
            Rating.created_at >= from_,
            Rating.created_at <= to_,
        )
    )
    row = result.one()
    raw_avg, count = row[0], row[1]
    return (float(raw_avg) if raw_avg is not None else None), int(count)
