"""Pydantic-схемы для домена команд: запросы и ответы.

TeamCreate/JoinTeamRequest/AddMemberRequest/SetRoleRequest — входящие данные.
TeamResponse/TeamMemberResponse — исходящие данные, from_attributes=True.
role в ответах отдаётся как str (.value), поскольку TeamRole — не str-enum.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class TeamCreate(BaseModel):
    """Запрос создания команды."""

    name: str


class JoinTeamRequest(BaseModel):
    """Запрос вступления в команду по invite-коду."""

    code: str


class AddMemberRequest(BaseModel):
    """Запрос добавления участника в команду."""

    user_id: uuid.UUID
    role: str = "member"


class SetRoleRequest(BaseModel):
    """Запрос изменения командной роли участника."""

    role: str


class TeamResponse(BaseModel):
    """Ответ с данными команды. invite_code включён — нужен создателю для приглашений."""

    id: uuid.UUID
    name: str
    invite_code: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    """Ответ с данными участника команды. role возвращается как строка (.value)."""

    team_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime

    model_config = {"from_attributes": True}
