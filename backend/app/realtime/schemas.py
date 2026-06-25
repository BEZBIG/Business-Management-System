"""Pydantic-схемы real-time событий: discriminated union envelope на 4 типа (D-10, D-11)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Data-модели (payload каждого типа события)
# ---------------------------------------------------------------------------


class JitsiLinkData(BaseModel):
    """Данные события «Jitsi-ссылка готова к встрече»."""

    meeting_id: uuid.UUID
    meeting_title: str
    jitsi_url: str
    start_time: datetime


class MeetingCancelledData(BaseModel):
    """Данные события «встреча отменена»."""

    meeting_id: uuid.UUID
    meeting_title: str
    cancelled_by: uuid.UUID


class DeadlineEscalationData(BaseModel):
    """Данные события «дедлайн задачи просрочен — эскалация»."""

    task_id: uuid.UUID
    task_title: str
    assignee_id: uuid.UUID
    deadline: datetime
    days_overdue: int


class DigestData(BaseModel):
    """Данные события «AI-дайджест готов»."""

    content: str  # текст дайджеста в формате markdown
    generated_at: datetime


# ---------------------------------------------------------------------------
# Event-классы с Literal-дискриминатором по полю type
# ---------------------------------------------------------------------------


class JitsiLinkEvent(BaseModel):
    """Событие доставки Jitsi-ссылки участникам встречи."""

    type: Literal["jitsi_link"]
    v: int = 1
    ts: datetime
    data: JitsiLinkData


class MeetingCancelledEvent(BaseModel):
    """Событие отмены встречи."""

    type: Literal["meeting_cancelled"]
    v: int = 1
    ts: datetime
    data: MeetingCancelledData


class DeadlineEscalationEvent(BaseModel):
    """Событие эскалации просроченного дедлайна задачи."""

    type: Literal["deadline_escalation"]
    v: int = 1
    ts: datetime
    data: DeadlineEscalationData


class DigestEvent(BaseModel):
    """Событие готового AI-дайджеста."""

    type: Literal["digest"]
    v: int = 1
    ts: datetime
    data: DigestData


# ---------------------------------------------------------------------------
# Top-level discriminated union alias (D-10)
# Дискриминатор по полю "type" — Pydantic выбирает нужный Event-класс автоматически.
# ---------------------------------------------------------------------------

RealtimeEvent = Annotated[
    JitsiLinkEvent | MeetingCancelledEvent | DeadlineEscalationEvent | DigestEvent,
    Field(discriminator="type"),
]
