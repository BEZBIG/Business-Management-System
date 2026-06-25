"""HTTP-слой домена встреч: создание, просмотр, отмена встреч и объединённый календарь.

Тонкие обработчики — вся логика в service.py.
Роутер встреч вложен в team-контекст: /teams/{team_id}/meetings.
Роутер календаря монтируется отдельно: /calendar.
RBAC: get_team_membership (404 для не-членов) + require_meeting_owner (403 для не-владельцев).

Публикация real-time событий (Jitsi-ссылки, отмена встречи) выполняется здесь —
ПОСЛЕ commit-а транзакции в get_async_session — чтобы исключить ghost-уведомления
и предотвратить откат транзакции при сбое Redis (CR-01).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.core.redis_client import redis_client
from app.db.session import get_async_session
from app.meetings.dependencies import get_meeting_or_404, require_meeting_owner
from app.meetings.models import Meeting
from app.meetings.schemas import CalendarEvent, MeetingCreate, MeetingResponse
from app.meetings.service import (
    cancel_meeting,
    create_meeting,
    get_calendar_events,
)
from app.realtime.publisher import publish_event
from app.realtime.schemas import (
    JitsiLinkData,
    JitsiLinkEvent,
    MeetingCancelledData,
    MeetingCancelledEvent,
)
from app.teams.dependencies import get_team_membership
from app.teams.models import TeamMember

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/teams/{team_id}/meetings", tags=["meetings"])
calendar_router = APIRouter(prefix="/calendar", tags=["calendar"])


def _to_meeting_response(meeting: Meeting, current_user_id: uuid.UUID) -> MeetingResponse:
    """Строит MeetingResponse из ORM-объекта Meeting.

    jitsi_url включается только для участников встречи (D-10):
    не-участник получает None — анти-перечисление приватных Jitsi-ссылок.
    Требует, чтобы meeting.participants был загружен через selectinload.
    """
    participant_ids = {p.user_id for p in meeting.participants}
    jitsi_url: str | None = None
    if current_user_id in participant_ids:
        jitsi_url = f"https://meet.jit.si/{meeting.jitsi_room_token}"

    return MeetingResponse(
        id=meeting.id,
        team_id=meeting.team_id,
        creator_id=meeting.creator_id,
        title=meeting.title,
        description=meeting.description,
        status=meeting.status.value,
        start_time=meeting.start_time,
        end_time=meeting.end_time,
        jitsi_url=jitsi_url,
        created_at=meeting.created_at,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_meeting_endpoint(
    team_id: uuid.UUID,
    data: MeetingCreate,
    membership: TeamMember = Depends(get_team_membership),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> MeetingResponse:
    """Создаёт встречу в команде. Любой член команды может создавать встречи.

    Конфликт по расписанию → 409 с detalями ConflictDetail.
    Нечлен команды в participant_ids → 422.

    Публикация Jitsi-ссылки выполняется после явного commit-а — исключает
    ghost-уведомления при откате транзакции и не откатывает БД при сбое Redis.
    """
    meeting = await create_meeting(
        session,
        team_id=team_id,
        creator_id=current_user.id,
        title=data.title,
        description=data.description,
        start_time=data.start_time,
        end_time=data.end_time,
        participant_ids=data.participant_ids,
    )
    # Явный commit до публикации: встреча гарантированно в БД (CR-01)
    await session.commit()

    # Публикуем Jitsi-ссылку каждому участнику (RT-02).
    # Сбой Redis не откатывает уже зафиксированную транзакцию.
    all_participants = {current_user.id, *data.participant_ids}
    jitsi_url = f"https://meet.jit.si/{meeting.jitsi_room_token}"
    for uid in all_participants:
        try:
            await publish_event(
                redis_client,
                str(uid),
                JitsiLinkEvent(
                    type="jitsi_link",
                    ts=datetime.now(UTC),
                    data=JitsiLinkData(
                        meeting_id=meeting.id,
                        meeting_title=meeting.title,
                        jitsi_url=jitsi_url,
                        start_time=meeting.start_time,
                    ),
                ),
            )
        except Exception:  # noqa: BLE001
            logger.warning("realtime_publish_failed", user_id=str(uid), meeting_id=str(meeting.id))

    logger.info("meetings_create", meeting_id=str(meeting.id), team_id=str(team_id))
    return _to_meeting_response(meeting, current_user.id)


@router.get("/{meeting_id}")
async def get_meeting_endpoint(
    team_id: uuid.UUID,
    meeting: Meeting = Depends(get_meeting_or_404),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> MeetingResponse:
    """Возвращает встречу по id.

    Не-член команды получает 404 (анти-энумерация, D-10).
    Отменённая встреча → 404 (через get_meeting_or_404 → get_meeting_detail).
    """
    return _to_meeting_response(meeting, current_user.id)


@router.delete("/{meeting_id}")
async def cancel_meeting_endpoint(
    team_id: uuid.UUID,
    meeting: Meeting = Depends(require_meeting_owner),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> dict[str, str]:
    """Отменяет встречу (soft-delete: status=CANCELLED). Только creator (D-03).

    Участник, не являющийся creator → 403.
    Не-член команды → 404 (через require_meeting_owner → get_meeting_or_404).

    Публикация meeting_cancelled выполняется после явного commit-а — исключает
    ghost-уведомления при откате транзакции и не откатывает БД при сбое Redis.
    """
    # Сохраняем участников до commit-а (после commit ORM-объект может быть detached)
    participants_snapshot = list(meeting.participants)

    await cancel_meeting(session, meeting)
    # Явный commit до публикации: статус CANCELLED гарантированно в БД (CR-01)
    await session.commit()

    # Уведомляем участников об отмене (RT-03a).
    # Сбой Redis не откатывает уже зафиксированную транзакцию.
    for p in participants_snapshot:
        try:
            await publish_event(
                redis_client,
                str(p.user_id),
                MeetingCancelledEvent(
                    type="meeting_cancelled",
                    ts=datetime.now(UTC),
                    data=MeetingCancelledData(
                        meeting_id=meeting.id,
                        meeting_title=meeting.title,
                        cancelled_by=meeting.creator_id,
                    ),
                ),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "realtime_publish_failed", user_id=str(p.user_id), meeting_id=str(meeting.id)
            )

    logger.info("meetings_cancel", meeting_id=str(meeting.id))
    return {"detail": "Meeting cancelled"}


@calendar_router.get("")
async def get_calendar_endpoint(
    from_dt: datetime,
    to_dt: datetime,
    view: str = "month",
    current_user: User = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> list[CalendarEvent]:
    """Возвращает объединённые события календаря (задачи + встречи) для текущего пользователя.

    view (month/week/day) — параметр для фронтенда (передаётся as-is,
    диапазон задаётся from_dt/to_dt).
    Задачи: assignee ИЛИ creator, дедлайн в [from_dt, to_dt] (D-16).
    Встречи: участник, status=ACTIVE, start_time в [from_dt, to_dt] (D-15).
    Результат отсортирован по start.
    """
    return await get_calendar_events(session, current_user.id, from_dt, to_dt)
