"""Бизнес-логика встреч: race-safe конфликт-детекция, Jitsi-токен, отмена, календарь.

Все функции принимают AsyncSession первым аргументом и не коммитят —
commit делает get_async_session. flush() используется для получения id до commit.

Порядок операций create_meeting (D-04..D-09):
  1. Валидация членства участников в команде (D-01)
  2. Advisory locks per participant в sorted-порядке (anti-deadlock, D-04)
  3. Conflict check SELECT с строгим < (D-05, D-07)
  4. INSERT Meeting с CSPRNG jitsi_room_token (D-09)
  5. Bulk INSERT MeetingParticipant (включая creator, D-02)

Сервисный слой намеренно не вызывает publish_event: публикация
real-time событий выполняется в router.py ПОСЛЕ commit-а транзакции.
"""

from __future__ import annotations

import secrets
import struct
import uuid
from datetime import datetime

import sqlalchemy as sa
import structlog
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.meetings.models import Meeting, MeetingParticipant, MeetingStatus
from app.meetings.schemas import CalendarEvent, ConflictDetail
from app.tasks.models import Task
from app.teams.service import get_team_member

logger = structlog.get_logger(__name__)


def _uuid_to_lock_key(uid: uuid.UUID) -> int:
    """Переводит UUID в signed int64 для pg_advisory_xact_lock.

    Берём нижние 64 бита UUID и интерпретируем как знаковый int64.
    Диапазон PG bigint: -2^63 .. 2^63-1 — struct.unpack обеспечивает знак.
    """
    low = uid.int & 0xFFFFFFFFFFFFFFFF
    result: int = struct.unpack(">q", struct.pack(">Q", low))[0]
    return result


async def _acquire_participant_locks(
    session: AsyncSession, participant_ids: list[uuid.UUID]
) -> None:
    """Берёт pg_advisory_xact_lock по каждому участнику в sorted-порядке.

    Детерминированный порядок (sorted) — anti-deadlock: все транзакции берут
    локи в одном и том же порядке, исключая циклическое ожидание (D-04).
    Локи привязаны к транзакции; освобождаются при session.commit().
    """
    for uid in sorted(participant_ids):
        key = _uuid_to_lock_key(uid)
        await session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": key},
        )


async def validate_participants_membership(
    session: AsyncSession,
    team_id: uuid.UUID,
    participant_ids: list[uuid.UUID],
) -> None:
    """Проверяет, что все participant_ids являются членами команды.

    Нечлен команды → HTTPException 422 (D-01).
    """
    for uid in participant_ids:
        member = await get_team_member(session, team_id, uid)
        if member is None:
            raise HTTPException(
                status_code=422,
                detail=f"Participant {uid} is not a member of the team",
            )


async def find_conflicts(
    session: AsyncSession,
    participant_ids: list[uuid.UUID],
    new_start: datetime,
    new_end: datetime,
    exclude_meeting_id: uuid.UUID | None = None,
) -> list[ConflictDetail]:
    """Возвращает конфликтующие встречи для каждого участника.

    Строгое < (Allen's overlap): back-to-back (A.end == B.start) НЕ конфликт (D-05).
    Фильтр status=ACTIVE: отменённые встречи исключаются (D-07).
    Возвращает список ConflictDetail — по одному на каждый (participant × conflicting meeting).
    """
    stmt = (
        select(
            MeetingParticipant.user_id,
            Meeting.id,
            Meeting.title,
            Meeting.start_time,
            Meeting.end_time,
        )
        .join(Meeting, MeetingParticipant.meeting_id == Meeting.id)
        .where(
            MeetingParticipant.user_id.in_(participant_ids),
            Meeting.status == MeetingStatus.ACTIVE,
            Meeting.start_time < new_end,  # строгий <
            Meeting.end_time > new_start,  # строгий >
        )
    )
    if exclude_meeting_id is not None:
        stmt = stmt.where(Meeting.id != exclude_meeting_id)

    rows = (await session.execute(stmt)).all()
    return [
        ConflictDetail(
            meeting_id=row.id,
            title=row.title,
            start_time=row.start_time,
            end_time=row.end_time,
            participant_id=row.user_id,
        )
        for row in rows
    ]


async def create_meeting(
    session: AsyncSession,
    team_id: uuid.UUID,
    creator_id: uuid.UUID,
    title: str,
    start_time: datetime,
    end_time: datetime,
    participant_ids: list[uuid.UUID],
    description: str | None = None,
) -> Meeting:
    """Создаёт встречу с гарантированно бесконфликтным слотом.

    Порядок операций внутри одной транзакции:
    1. Валидация членства участников в команде (D-01)
    2. Advisory locks по all_participants в sorted-порядке (D-04)
    3. Conflict check (D-05, D-07)
    4. INSERT Meeting + jitsi_room_token (D-09)
    5. Bulk INSERT MeetingParticipant (D-02)
    """
    # Валидация членства до локов (membership check не требует гонки)
    await validate_participants_membership(session, team_id, participant_ids)

    # Собираем всех участников (creator тоже участник, D-02); дедупликация через set
    all_participants = list({creator_id, *participant_ids})

    # Advisory locks — race-free проверка конфликтов
    await _acquire_participant_locks(session, all_participants)

    # Conflict check
    conflicts = await find_conflicts(session, all_participants, start_time, end_time)
    if conflicts:
        raise HTTPException(
            status_code=409,
            detail=[c.model_dump() for c in conflicts],
        )

    # Создание встречи
    meeting = Meeting(
        team_id=team_id,
        creator_id=creator_id,
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        status=MeetingStatus.ACTIVE,
        jitsi_room_token=secrets.token_urlsafe(32),
    )
    session.add(meeting)
    await session.flush()  # получаем meeting.id до добавления участников

    # Bulk insert участников
    for uid in all_participants:
        session.add(MeetingParticipant(meeting_id=meeting.id, user_id=uid))
    await session.flush()

    logger.info("meeting_created", meeting_id=str(meeting.id), team_id=str(team_id))

    return meeting


async def cancel_meeting(session: AsyncSession, meeting: Meeting) -> None:
    """Отменяет встречу через soft-delete: status=CANCELLED (D-12).

    Hard-delete отсутствует. Отменённые встречи исключаются из конфликт-чека (D-07).
    """
    meeting.status = MeetingStatus.CANCELLED
    await session.flush()
    logger.info("meeting_cancelled", meeting_id=str(meeting.id))


async def get_meeting_detail(
    session: AsyncSession, meeting_id: uuid.UUID
) -> Meeting | None:
    """Загружает активную встречу с участниками через selectinload.

    selectinload(Meeting.participants) — обязателен (lazy="raise", Pitfall 3).
    Возвращает None если встреча не найдена или отменена.
    """
    result = await session.execute(
        select(Meeting)
        .where(Meeting.id == meeting_id, Meeting.status == MeetingStatus.ACTIVE)
        .options(selectinload(Meeting.participants))
    )
    return result.scalar_one_or_none()


async def get_calendar_events(
    session: AsyncSession,
    user_id: uuid.UUID,
    from_dt: datetime,
    to_dt: datetime,
) -> list[CalendarEvent]:
    """Возвращает задачи + встречи пользователя в диапазоне [from_dt, to_dt].

    Задачи: где пользователь assignee ИЛИ creator, с дедлайном в диапазоне (D-16).
    Встречи: где пользователь участник, status=ACTIVE, start_time в диапазоне (D-15).
    Задача-точка: start=end=deadline, is_point_event=True.
    Результат отсортирован по start.
    """
    # SELECT задач
    tasks_stmt = select(Task).where(
        Task.is_deleted.is_(False),
        Task.deadline.is_not(None),
        Task.deadline >= from_dt,
        Task.deadline <= to_dt,
        sa.or_(Task.assignee_id == user_id, Task.creator_id == user_id),
    )
    tasks = list((await session.execute(tasks_stmt)).scalars().all())

    # SELECT встреч (через participant join)
    meetings_stmt = (
        select(Meeting)
        .join(MeetingParticipant, Meeting.id == MeetingParticipant.meeting_id)
        .where(
            MeetingParticipant.user_id == user_id,
            Meeting.status == MeetingStatus.ACTIVE,
            Meeting.start_time >= from_dt,
            Meeting.start_time <= to_dt,
        )
        .options(selectinload(Meeting.participants))
    )
    meetings = list((await session.execute(meetings_stmt)).scalars().all())

    # Python merge
    events: list[CalendarEvent] = []
    for t in tasks:
        events.append(
            CalendarEvent(
                type="task",
                id=t.id,
                title=t.title,
                start=t.deadline,  # type: ignore[arg-type]
                end=t.deadline,  # type: ignore[arg-type]
                is_point_event=True,
            )
        )
    for m in meetings:
        events.append(
            CalendarEvent(
                type="meeting",
                id=m.id,
                title=m.title,
                start=m.start_time,
                end=m.end_time,
            )
        )

    events.sort(key=lambda e: e.start)
    return events


def build_meeting_response_jitsi_url(
    meeting: Meeting, current_user_id: uuid.UUID
) -> str | None:
    """Возвращает jitsi_url только для участников встречи (D-10).

    Не-участник получает None — анти-перечисление приватных URL.
    Требует, чтобы meeting.participants был загружен через selectinload.
    """
    participant_ids = {p.user_id for p in meeting.participants}
    if current_user_id not in participant_ids:
        return None
    return f"https://meet.jit.si/{meeting.jitsi_room_token}"


def get_jitsi_url_for_user(meeting: Meeting, user_id: uuid.UUID) -> str | None:
    """Возвращает jitsi_url если user_id является участником встречи (D-10).

    Алиас build_meeting_response_jitsi_url для использования в роутере.
    """
    return build_meeting_response_jitsi_url(meeting, user_id)


