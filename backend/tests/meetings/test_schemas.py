"""Юнит-тесты Pydantic-схем встреч."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.meetings.schemas import MAX_PARTICIPANTS, MeetingCreate


def _future(delta: timedelta = timedelta(hours=1)) -> datetime:
    """Возвращает datetime в будущем (UTC-aware)."""
    return datetime.now(UTC) + delta


def _valid_create(**kwargs: object) -> MeetingCreate:
    """Создаёт валидный MeetingCreate с настройками по умолчанию."""
    defaults: dict[str, object] = {
        "title": "Standup",
        "start_time": _future(timedelta(hours=1)),
        "end_time": _future(timedelta(hours=2)),
        "participant_ids": [],
    }
    defaults.update(kwargs)
    return MeetingCreate.model_validate(defaults)


def test_time_validation() -> None:
    """D-13: start >= end / прошедшее время / длительность вне границ → 422 (ValidationError)."""
    # start >= end → ошибка
    with pytest.raises(ValidationError):
        MeetingCreate(
            title="Bad",
            start_time=_future(timedelta(hours=2)),
            end_time=_future(timedelta(hours=1)),
        )

    # start == end → ошибка
    t = _future(timedelta(hours=1))
    with pytest.raises(ValidationError):
        MeetingCreate(title="Bad", start_time=t, end_time=t)

    # start в прошлом → ошибка
    with pytest.raises(ValidationError):
        MeetingCreate(
            title="Bad",
            start_time=_future(timedelta(hours=-2)),
            end_time=_future(timedelta(hours=-1)),
        )

    # Длительность менее 5 минут → ошибка
    with pytest.raises(ValidationError):
        MeetingCreate(
            title="Bad",
            start_time=_future(timedelta(hours=1)),
            end_time=_future(timedelta(hours=1, minutes=3)),
        )

    # Длительность более 8 часов → ошибка
    with pytest.raises(ValidationError):
        MeetingCreate(
            title="Bad",
            start_time=_future(timedelta(hours=1)),
            end_time=_future(timedelta(hours=10)),
        )

    # Timezone-naive start_time → ошибка
    with pytest.raises(ValidationError):
        MeetingCreate(
            title="Bad",
            start_time=datetime.now() + timedelta(hours=1),  # naive
            end_time=_future(timedelta(hours=2)),
        )

    # Корректная встреча длиной 1 час → успех
    m = _valid_create()
    assert m.title == "Standup"


def test_max_participants() -> None:
    """D-14: более MAX_PARTICIPANTS участников → ValidationError; ровно MAX_PARTICIPANTS допустимо."""
    # Ровно MAX_PARTICIPANTS → допустимо
    ids_ok = [uuid.uuid4() for _ in range(MAX_PARTICIPANTS)]
    m = _valid_create(participant_ids=ids_ok)
    assert len(m.participant_ids) == MAX_PARTICIPANTS

    # MAX_PARTICIPANTS + 1 → ошибка
    ids_bad = [uuid.uuid4() for _ in range(MAX_PARTICIPANTS + 1)]
    with pytest.raises(ValidationError):
        _valid_create(participant_ids=ids_bad)
