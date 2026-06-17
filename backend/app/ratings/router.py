"""HTTP-слой домена оценок: submit рейтинга и query средних оценок.

Тонкие обработчики — вся логика в service.py.
POST /teams/{team_id}/tasks/{task_id}/ratings — submit оценки (D-13).
GET  /users/{user_id}/ratings/average        — all-time среднее (RATE-02).
GET  /users/{user_id}/ratings/average?from=&to= — среднее за период (RATE-03).

RBAC (D-13): оценивать могут создатель задачи + manager/owner команды.
Не-член команды → 404 (через get_task_or_404 → get_team_membership).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.db.session import get_async_session
from app.ratings.schemas import RatingUpsert, UserRatingStats
from app.ratings.service import (
    get_avg_rating_alltime,
    get_avg_rating_period,
    upsert_rating,
    validate_rating_state,
)
from app.tasks.dependencies import get_task_or_404
from app.tasks.models import Task
from app.teams.dependencies import get_team_membership
from app.teams.models import TeamMember, TeamRole

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ratings"])
users_ratings_router = APIRouter(prefix="/users", tags=["ratings"])


@router.post("/teams/{team_id}/tasks/{task_id}/ratings")
async def submit_rating(
    team_id: uuid.UUID,
    data: RatingUpsert,
    task: Task = Depends(get_task_or_404),  # noqa: B008
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> UserRatingStats:
    """Выставляет оценку 1–5 за выполненную задачу (RATE-01, D-13, D-14).

    Разрешено: создатель задачи ИЛИ manager/owner команды.
    Остальные члены → 403. Не-члены → 404 (через get_task_or_404).
    status != done → 422. Самооценка → 403. Повторно → upsert (D-14).
    """
    # D-13: только creator задачи + manager/owner команды
    is_creator = task.creator_id == current_user.id
    is_privileged = membership.role in (TeamRole.OWNER, TeamRole.MANAGER)

    if not (is_creator or is_privileged):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the task creator or team manager/owner can submit ratings",
        )

    # Guards: status==done, assignee есть, rater!=ratee
    validate_rating_state(task, current_user.id)

    ratee_id = task.assignee_id  # D-12: ratee = assignee
    assert ratee_id is not None  # validate_rating_state уже проверила

    await upsert_rating(
        session,
        task_id=task.id,
        rater_id=current_user.id,
        ratee_id=ratee_id,
        score=data.score,
    )

    # Возвращаем актуальную статистику (D-15: немедленное обновление)
    avg, count = await get_avg_rating_alltime(session, ratee_id)
    logger.info(
        "rating_submitted",
        task_id=str(task.id),
        rater_id=str(current_user.id),
        score=data.score,
    )
    return UserRatingStats(ratee_id=ratee_id, average=avg, count=count)


@users_ratings_router.get("/{user_id}/ratings/average")
async def get_average_rating(
    user_id: uuid.UUID,
    from_: datetime | None = Query(default=None, alias="from"),  # noqa: B008
    to_: datetime | None = Query(default=None, alias="to"),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> UserRatingStats:
    """Возвращает среднюю оценку пользователя (RATE-02/03, D-15).

    Без from/to → all-time среднее (RATE-02).
    С from/to → среднее за период (RATE-03).
    Среднее пересчитывается немедленно — без кэша (D-15).
    Доступно аутентифицированным пользователям (T-03-20 accept).
    """
    if from_ is not None and to_ is not None:
        avg, count = await get_avg_rating_period(session, user_id, from_, to_)
    else:
        avg, count = await get_avg_rating_alltime(session, user_id)

    return UserRatingStats(ratee_id=user_id, average=avg, count=count)
