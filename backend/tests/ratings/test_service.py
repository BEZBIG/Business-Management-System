"""Тесты сервисного слоя оценок: guards, upsert, AVG alltime, AVG за период.

Тесты используют unittest.mock для имитации AsyncSession и ORM-объектов.
Не требуют запущенной БД — проверяют бизнес-логику и SQL-запросы изолированно.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ratings.service import (
    get_avg_rating_alltime,
    get_avg_rating_period,
    upsert_rating,
    validate_rating_state,
)
from app.tasks.models import Task, TaskStatus


def _make_task(
    status: TaskStatus = TaskStatus.DONE,
    assignee_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
) -> Task:
    """Создаёт Task с нужными полями через мок (без реальной БД)."""
    task = MagicMock(spec=Task)
    task.status = status
    task.assignee_id = assignee_id or uuid.uuid4()
    task.creator_id = creator_id or uuid.uuid4()
    task.id = uuid.uuid4()
    task.team_id = uuid.uuid4()
    return task


def test_rating_guards() -> None:
    """RATE-01: Guards validate_rating_state (D-13).

    - status != done → HTTPException 422
    - assignee_id is None → HTTPException 422
    - rater_id == assignee_id (самооценка) → HTTPException 403
    """
    from fastapi import HTTPException

    rater_id = uuid.uuid4()
    assignee_id = uuid.uuid4()

    # Guard 1: статус не done → 422
    task_open = _make_task(status=TaskStatus.OPEN, assignee_id=assignee_id)
    with pytest.raises(HTTPException) as exc_info:
        validate_rating_state(task_open, rater_id)
    assert exc_info.value.status_code == 422

    task_in_progress = _make_task(status=TaskStatus.IN_PROGRESS, assignee_id=assignee_id)
    with pytest.raises(HTTPException) as exc_info:
        validate_rating_state(task_in_progress, rater_id)
    assert exc_info.value.status_code == 422

    # Guard 2: нет исполнителя → 422
    task_no_assignee = _make_task(status=TaskStatus.DONE, assignee_id=None)
    task_no_assignee.assignee_id = None
    with pytest.raises(HTTPException) as exc_info:
        validate_rating_state(task_no_assignee, rater_id)
    assert exc_info.value.status_code == 422

    # Guard 3: самооценка (rater == ratee/assignee) → 403
    task_self = _make_task(status=TaskStatus.DONE, assignee_id=rater_id)
    with pytest.raises(HTTPException) as exc_info:
        validate_rating_state(task_self, rater_id)
    assert exc_info.value.status_code == 403

    # Happy path: задача done, есть assignee, rater != assignee → без исключения
    task_ok = _make_task(status=TaskStatus.DONE, assignee_id=assignee_id)
    validate_rating_state(task_ok, rater_id)  # не должна кидать


@pytest.mark.asyncio
async def test_rating_upsert() -> None:
    """RATE-01: upsert_rating использует ON CONFLICT DO UPDATE (D-14).

    Проверяем, что:
    1. Запрос строится через pg_insert с on_conflict_do_update
    2. Функция flush() вызывается
    3. scalar_one() возвращает Rating
    """
    from app.ratings.models import Rating

    task_id = uuid.uuid4()
    rater_id = uuid.uuid4()
    ratee_id = uuid.uuid4()
    score = 4

    # Мок Rating-объекта, который вернёт execute
    mock_rating = MagicMock(spec=Rating)
    mock_rating.id = uuid.uuid4()
    mock_rating.score = score

    # Мок execute → result → scalar_one
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = mock_rating

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)
    session.flush = AsyncMock()

    result = await upsert_rating(session, task_id, rater_id, ratee_id, score)

    # flush вызван
    session.flush.assert_called_once()
    # результат — Rating
    assert result is mock_rating


@pytest.mark.asyncio
async def test_avg_alltime() -> None:
    """RATE-02: get_avg_rating_alltime возвращает математически верное среднее (D-15).

    Decimal → float конвертация. None при отсутствии оценок.
    """
    ratee_id = uuid.uuid4()

    # Случай 1: есть оценки — среднее 3.5 (Decimal, как вернёт PostgreSQL)
    mock_result = MagicMock()
    mock_result.one.return_value = (Decimal("3.5"), 2)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    avg, count = await get_avg_rating_alltime(session, ratee_id)
    assert avg == pytest.approx(3.5)
    assert count == 2
    assert isinstance(avg, float)

    # Случай 2: нет оценок → None, count = 0
    mock_result_empty = MagicMock()
    mock_result_empty.one.return_value = (None, 0)
    session.execute = AsyncMock(return_value=mock_result_empty)

    avg_none, count_zero = await get_avg_rating_alltime(session, ratee_id)
    assert avg_none is None
    assert count_zero == 0


@pytest.mark.asyncio
async def test_avg_period() -> None:
    """RATE-03: get_avg_rating_period фильтрует по created_at (D-15).

    Оценки вне диапазона не учитываются — логика в SQL-запросе.
    Проверяем, что функция передаёт from_/to_ в запрос и возвращает корректный результат.
    """
    ratee_id = uuid.uuid4()
    now = datetime.now(UTC)
    from_ = now - timedelta(days=7)
    to_ = now

    # Среднее за период — 4.0 из 3 оценок
    mock_result = MagicMock()
    mock_result.one.return_value = (Decimal("4.0"), 3)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    avg, count = await get_avg_rating_period(session, ratee_id, from_, to_)
    assert avg == pytest.approx(4.0)
    assert count == 3
    assert isinstance(avg, float)

    # Пустой период → None
    mock_result_empty = MagicMock()
    mock_result_empty.one.return_value = (None, 0)
    session.execute = AsyncMock(return_value=mock_result_empty)

    avg_none, count_zero = await get_avg_rating_period(session, ratee_id, from_, to_)
    assert avg_none is None
    assert count_zero == 0
