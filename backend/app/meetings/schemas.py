"""Pydantic-схемы домена встреч: создание, ответ, детали конфликта и событие календаря."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, model_validator

# Константы валидации времени и состава встречи
MIN_DURATION: timedelta = timedelta(minutes=5)
MAX_DURATION: timedelta = timedelta(hours=8)
MAX_PARTICIPANTS: int = 50

# Допуск на расхождение часов между клиентом и сервером (1 минута)
_CLOCK_SKEW: timedelta = timedelta(minutes=1)


class MeetingCreate(BaseModel):
    """Запрос создания встречи с валидацией временного диапазона и состава участников."""

    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    participant_ids: list[uuid.UUID] = []

    @model_validator(mode="after")
    def validate_times(self) -> MeetingCreate:
        """Проверяет временные ограничения и лимит участников.

        Правила:
        - start_time должен быть timezone-aware (Pitfall 6)
        - start_time < end_time (D-13)
        - start_time не в прошлом с допуском ~1 мин на расхождение часов (D-13)
        - длительность от MIN_DURATION до MAX_DURATION включительно (D-13)
        - количество participant_ids не более MAX_PARTICIPANTS (D-14)
        """
        start = self.start_time
        end = self.end_time

        # Проверка timezone-aware (Pitfall 6)
        if start.tzinfo is None:
            raise ValueError("start_time должен содержать tzinfo (timezone-aware)")
        if end.tzinfo is None:
            raise ValueError("end_time должен содержать tzinfo (timezone-aware)")

        # start < end
        if start >= end:
            raise ValueError("start_time должен быть раньше end_time")

        # start не в прошлом (с допуском на расхождение часов)
        earliest_allowed = datetime.now(UTC) - _CLOCK_SKEW
        if start < earliest_allowed:
            raise ValueError("start_time не может быть в прошлом")

        # Длительность в допустимом диапазоне
        duration = end - start
        if duration < MIN_DURATION:
            raise ValueError(
                f"Длительность встречи не может быть менее {MIN_DURATION.seconds // 60} минут"
            )
        max_hours = int(MAX_DURATION.total_seconds() // 3600)
        if duration > MAX_DURATION:
            raise ValueError(
                f"Длительность встречи не может превышать {max_hours} часов"
            )

        # Лимит участников (D-14)
        if len(self.participant_ids) > MAX_PARTICIPANTS:
            raise ValueError(
                f"Количество участников не может превышать {MAX_PARTICIPANTS}"
            )

        return self


class MeetingResponse(BaseModel):
    """Ответ с данными встречи.

    jitsi_url включается только для участников встречи (D-10);
    для не-участников поле равно None.
    status возвращается как строка (.value из enum).
    """

    id: uuid.UUID
    team_id: uuid.UUID
    creator_id: uuid.UUID
    title: str
    description: str | None
    status: str
    start_time: datetime
    end_time: datetime
    jitsi_url: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConflictDetail(BaseModel):
    """Детали одного конфликта расписания в ответе 409.

    participant_id указывает, кто именно занят в данном временном слоте (D-08).
    """

    meeting_id: uuid.UUID
    title: str
    start_time: datetime
    end_time: datetime
    participant_id: uuid.UUID


class CalendarEvent(BaseModel):
    """Событие в объединённом календаре (задача или встреча).

    type — дискриминатор: "task" | "meeting" (D-15).
    is_point_event=True для задач с дедлайном (start == end == deadline).
    """

    type: str
    id: uuid.UUID
    title: str
    start: datetime
    end: datetime
    is_point_event: bool = False
