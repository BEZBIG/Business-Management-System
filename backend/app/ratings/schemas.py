"""Pydantic-схемы для домена оценок: запрос upsert и ответ со средней оценкой."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator


class RatingUpsert(BaseModel):
    """Запрос на выставление оценки 1–5 за выполненную задачу (D-13, RATE-01)."""

    score: int

    @field_validator("score")
    @classmethod
    def validate_score_range(cls, v: int) -> int:
        """Проверяет, что оценка находится в допустимом диапазоне 1–5."""
        if not 1 <= v <= 5:
            raise ValueError("Score must be between 1 and 5")
        return v


class UserRatingStats(BaseModel):
    """Статистика оценок пользователя: средняя оценка и количество оценок (RATE-02/03)."""

    ratee_id: uuid.UUID
    average: float | None
    count: int

    model_config = {"from_attributes": True}
