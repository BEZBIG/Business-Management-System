"""Pydantic-схемы домена задач: создание, обновление, ответ с вложенными комментариями."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TaskCreate(BaseModel):
    """Запрос создания задачи (D-05..D-10)."""

    title: str
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    deadline: datetime | None = None


class TaskUpdate(BaseModel):
    """Запрос обновления задачи. Все поля опциональны (partial update)."""

    title: str | None = None
    description: str | None = None
    assignee_id: uuid.UUID | None = None
    deadline: datetime | None = None
    status: str | None = None


class TaskCommentCreate(BaseModel):
    """Запрос создания комментария к задаче."""

    body: str


class TaskCommentResponse(BaseModel):
    """Ответ с данными комментария (D-11)."""

    id: uuid.UUID
    author_id: uuid.UUID | None
    body: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskResponse(BaseModel):
    """Полный ответ задачи с вложенными комментариями (D-09, D-10, D-11).

    status возвращается как str (.value из enum).
    comments — массив TaskCommentResponse, загруженных через selectinload.
    """

    id: uuid.UUID
    team_id: uuid.UUID
    creator_id: uuid.UUID
    assignee_id: uuid.UUID | None
    title: str
    description: str | None
    status: str
    deadline: datetime | None
    is_deleted: bool
    comments: list[TaskCommentResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}
