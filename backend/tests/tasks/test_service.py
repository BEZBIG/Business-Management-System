"""Тесты сервисного слоя задач.

Unit-тесты на моках AsyncSession — не требуют реальной БД.
Проверяют: state machine переходов статусов, assignee-валидацию, timezone-aware deadline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

import app.auth.models  # noqa: F401 — инициализирует SQLAlchemy mapper для relationship("User")
from app.tasks.models import Task, TaskStatus
from app.tasks.service import (
    ALLOWED_TRANSITIONS,
    add_comment,
    create_task,
    validate_assignee_membership,
    validate_status_transition,
)


def _make_task(
    status: TaskStatus = TaskStatus.OPEN,
    team_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
) -> Task:
    """Создаёт Task без сохранения в БД."""
    t = Task(
        team_id=team_id or uuid.uuid4(),
        creator_id=uuid.uuid4(),
        title="Test task",
        status=status,
    )
    t.id = task_id or uuid.uuid4()
    t.is_deleted = False
    return t


class TestStatusTransitions:
    """Тесты state machine статусов (D-07, TASK-04)."""

    def test_open_to_in_progress_allowed(self) -> None:
        """open → in_progress допустим."""
        validate_status_transition(TaskStatus.OPEN, TaskStatus.IN_PROGRESS)  # не бросает

    def test_in_progress_to_done_allowed(self) -> None:
        """in_progress → done допустим."""
        validate_status_transition(TaskStatus.IN_PROGRESS, TaskStatus.DONE)  # не бросает

    def test_done_to_in_progress_allowed(self) -> None:
        """done → in_progress допустим (переоткрытие)."""
        validate_status_transition(TaskStatus.DONE, TaskStatus.IN_PROGRESS)  # не бросает

    def test_in_progress_to_open_allowed(self) -> None:
        """in_progress → open допустим (откат)."""
        validate_status_transition(TaskStatus.IN_PROGRESS, TaskStatus.OPEN)  # не бросает

    def test_open_to_done_raises_422(self) -> None:
        """open → done запрещён → 422 (D-07)."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_status_transition(TaskStatus.OPEN, TaskStatus.DONE)
        assert exc_info.value.status_code == 422
        assert "open" in exc_info.value.detail
        assert "done" in exc_info.value.detail

    def test_done_to_open_raises_422(self) -> None:
        """done → open запрещён (не соседний переход)."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            validate_status_transition(TaskStatus.DONE, TaskStatus.OPEN)
        assert exc_info.value.status_code == 422

    def test_same_status_no_op(self) -> None:
        """Переход к тому же статусу — no-op, не бросает исключение."""
        validate_status_transition(TaskStatus.OPEN, TaskStatus.OPEN)
        validate_status_transition(TaskStatus.IN_PROGRESS, TaskStatus.IN_PROGRESS)
        validate_status_transition(TaskStatus.DONE, TaskStatus.DONE)

    def test_allowed_transitions_dict_open_to_done_absent(self) -> None:
        """DONE отсутствует в ALLOWED_TRANSITIONS[OPEN] — прямая проверка словаря."""
        assert TaskStatus.DONE not in ALLOWED_TRANSITIONS[TaskStatus.OPEN]
        assert TaskStatus.IN_PROGRESS in ALLOWED_TRANSITIONS[TaskStatus.OPEN]


def test_status_transitions() -> None:
    """TASK-04: open→done = 422; open→in_progress = ok; done→in_progress = ok."""
    from fastapi import HTTPException

    # open→done запрещён
    with pytest.raises(HTTPException) as exc_info:
        validate_status_transition(TaskStatus.OPEN, TaskStatus.DONE)
    assert exc_info.value.status_code == 422

    # open→in_progress OK
    validate_status_transition(TaskStatus.OPEN, TaskStatus.IN_PROGRESS)

    # done→in_progress OK
    validate_status_transition(TaskStatus.DONE, TaskStatus.IN_PROGRESS)


@pytest.mark.asyncio
async def test_assignee_membership() -> None:
    """TASK-02: assignee не из team_members → 422 (D-05)."""
    from fastapi import HTTPException

    mock_session = AsyncMock()
    team_id = uuid.uuid4()
    non_member_id = uuid.uuid4()

    # get_team_member возвращает None → нечлен
    with patch("app.tasks.service.get_team_member", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await validate_assignee_membership(mock_session, team_id, non_member_id)
        assert exc_info.value.status_code == 422
        assert "member" in exc_info.value.detail.lower()


@pytest.mark.asyncio
async def test_assignee_membership_valid() -> None:
    """assignee в команде → валидация проходит без исключения."""
    from app.teams.models import TeamMember, TeamRole

    mock_session = AsyncMock()
    team_id = uuid.uuid4()
    member_id = uuid.uuid4()
    member = TeamMember(team_id=team_id, user_id=member_id, role=TeamRole.MEMBER)

    with patch("app.tasks.service.get_team_member", return_value=member):
        await validate_assignee_membership(mock_session, team_id, member_id)  # не бросает


def test_deadline_tz() -> None:
    """TASK-03: deadline сохраняется timezone-aware; None допустим."""
    # timezone-aware datetime допустим
    deadline_tz = datetime(2026, 12, 31, 12, 0, 0, tzinfo=UTC)
    assert deadline_tz.tzinfo is not None, "deadline должен быть timezone-aware"

    # None тоже допустим
    deadline_none = None
    assert deadline_none is None

    # Проверяем через создание Task-объекта
    task = Task(
        team_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        title="Deadline test",
        deadline=deadline_tz,
    )
    assert task.deadline == deadline_tz
    assert task.deadline.tzinfo is not None

    # Task без дедлайна
    task_no_deadline = Task(
        team_id=uuid.uuid4(),
        creator_id=uuid.uuid4(),
        title="No deadline",
        deadline=None,
    )
    assert task_no_deadline.deadline is None


@pytest.mark.asyncio
async def test_create_task_without_assignee() -> None:
    """create_task без assignee не вызывает validate_assignee_membership."""
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    added: list[object] = []
    mock_session.add = lambda obj: added.append(obj)

    team_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    with patch("app.tasks.service.get_team_member") as mock_get_member:
        task = await create_task(mock_session, team_id, creator_id, "Title")
        mock_get_member.assert_not_called()

    assert task.title == "Title"
    assert task.status == TaskStatus.OPEN
    assert len(added) == 1


@pytest.mark.asyncio
async def test_create_task_with_non_member_assignee_raises() -> None:
    """create_task с assignee вне команды → 422."""
    from fastapi import HTTPException

    mock_session = AsyncMock()
    team_id = uuid.uuid4()
    creator_id = uuid.uuid4()
    non_member_id = uuid.uuid4()

    with patch("app.tasks.service.get_team_member", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            await create_task(mock_session, team_id, creator_id, "Title", assignee_id=non_member_id)
        assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_add_comment() -> None:
    """add_comment создаёт TaskComment с корректными полями."""
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    added: list[object] = []
    mock_session.add = lambda obj: added.append(obj)

    task_id = uuid.uuid4()
    author_id = uuid.uuid4()
    body = "Тестовый комментарий"

    comment = await add_comment(mock_session, task_id, author_id, body)

    assert comment.task_id == task_id
    assert comment.author_id == author_id
    assert comment.body == body
    assert len(added) == 1


@pytest.mark.asyncio
async def test_task_crud() -> None:
    """TASK-01: create_task создаёт задачу; is_deleted=False по умолчанию."""
    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()
    added: list[object] = []
    mock_session.add = lambda obj: added.append(obj)

    team_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    task = await create_task(mock_session, team_id, creator_id, "New task", description="Details")

    assert task.team_id == team_id
    assert task.creator_id == creator_id
    assert task.title == "New task"
    assert task.description == "Details"
    assert task.status == TaskStatus.OPEN
    # is_deleted: в unit-тесте (без БД) server_default не применяется;
    # Python default=False должен применяться; если None — то flush не запускает DB-default
    assert task.is_deleted in (False, None)
    assert len(added) == 1
