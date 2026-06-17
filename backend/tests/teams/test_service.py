"""Тесты сервисного слоя команд.

Unit-тесты на моках AsyncSession — не требуют реальной БД.
Проверяют: создание команды с invite_code, owner-роль, идемпотентность join,
отклонение неверного кода, защиту от удаления последнего owner.

app.auth.models импортируется на уровне модуля для инициализации SQLAlchemy mapper
до создания ORM-объектов в тестах.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.auth.models  # noqa: F401 — инициализирует SQLAlchemy mapper для relationship("User")
from app.teams.models import Team, TeamMember, TeamRole
from app.teams.service import (
    create_team,
    join_team,
    remove_member,
)


@pytest.mark.asyncio
async def test_create_team() -> None:
    """TEAM-01: create_team генерирует invite_code и создаёт TeamMember с ролью OWNER."""
    mock_session = AsyncMock()
    added_objects: list[object] = []

    def capture_add(obj: object) -> None:
        added_objects.append(obj)

    mock_session.add = capture_add

    team_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    async def mock_flush() -> None:
        # После первого flush устанавливаем id команды (имитирует DB)
        if added_objects and hasattr(added_objects[0], "invite_code"):
            added_objects[0].id = team_id

    mock_session.flush = mock_flush

    team = await create_team(mock_session, "Test Team", creator_id)

    # invite_code должен быть непустым (secrets.token_urlsafe(32))
    assert team.invite_code, "invite_code должен быть сгенерирован"
    assert len(team.invite_code) > 0, "invite_code не должен быть пустым"

    # Должны быть добавлены team и TeamMember
    assert len(added_objects) == 2, f"Ожидали 2 объекта, получили {len(added_objects)}"

    # Второй объект — TeamMember с ролью OWNER
    member = added_objects[1]
    assert isinstance(member, TeamMember), "Второй объект должен быть TeamMember"
    assert member.role == TeamRole.OWNER, "Создатель должен получить роль OWNER (D-01)"
    assert member.user_id == creator_id, "user_id должен совпадать с creator_id"


@pytest.mark.asyncio
async def test_join_team_valid_code() -> None:
    """TEAM-02: join_team с верным кодом создаёт TeamMember."""
    team = Team(name="Alpha", invite_code="validcode123")
    team.id = uuid.uuid4()

    user_id = uuid.uuid4()
    added_objects: list[object] = []

    mock_session = AsyncMock()
    mock_session.flush = AsyncMock()

    def capture_add(obj: object) -> None:
        added_objects.append(obj)

    mock_session.add = capture_add

    with (
        patch("app.teams.service.get_team_by_invite_code", return_value=team),
        patch("app.teams.service.get_team_member", return_value=None),
    ):
        result = await join_team(mock_session, "validcode123", user_id)

    assert result is not None, "join_team должен вернуть TeamMember при верном коде"
    assert isinstance(result, TeamMember), "Результат должен быть TeamMember"
    assert result.role == TeamRole.MEMBER, "Новый участник должен получить роль MEMBER"
    assert result.user_id == user_id


@pytest.mark.asyncio
async def test_join_team_invalid_code() -> None:
    """TEAM-02: join_team с неверным кодом возвращает None (не исключение)."""
    mock_session = AsyncMock()

    with patch("app.teams.service.get_team_by_invite_code", return_value=None):
        result = await join_team(mock_session, "wrongcode", uuid.uuid4())

    assert result is None, "join_team должен вернуть None при неверном коде"


@pytest.mark.asyncio
async def test_join_team_idempotent() -> None:
    """TEAM-02: повторный join тем же пользователем не создаёт второй TeamMember (D-02)."""
    team = Team(name="Beta", invite_code="code456")
    team.id = uuid.uuid4()

    user_id = uuid.uuid4()
    existing_member = TeamMember(team_id=team.id, user_id=user_id, role=TeamRole.MEMBER)

    mock_session = AsyncMock()
    added_objects: list[object] = []

    def capture_add(obj: object) -> None:
        added_objects.append(obj)

    mock_session.add = capture_add

    with (
        patch("app.teams.service.get_team_by_invite_code", return_value=team),
        patch("app.teams.service.get_team_member", return_value=existing_member),
    ):
        result = await join_team(mock_session, "code456", user_id)

    assert result is existing_member, "Повторный join должен вернуть существующее членство"
    assert len(added_objects) == 0, "session.add не должен вызываться при повторном join"


@pytest.mark.asyncio
async def test_remove_member_last_owner_raises() -> None:
    """T-03-09: remove_member запрещает удаление последнего owner команды."""
    team_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    owner_member = TeamMember(team_id=team_id, user_id=owner_id, role=TeamRole.OWNER)

    mock_session = AsyncMock()
    # Нет других owner-ов
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = execute_result

    with patch("app.teams.service.get_team_member", return_value=owner_member):
        with pytest.raises(ValueError, match="last owner"):
            await remove_member(mock_session, team_id, owner_id)


@pytest.mark.asyncio
async def test_remove_member_owner_with_other_owner_succeeds() -> None:
    """remove_member разрешает удаление owner, если есть второй owner."""
    team_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    other_owner_id = uuid.uuid4()
    owner_member = TeamMember(team_id=team_id, user_id=owner_id, role=TeamRole.OWNER)
    other_owner = TeamMember(team_id=team_id, user_id=other_owner_id, role=TeamRole.OWNER)

    mock_session = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = other_owner
    mock_session.execute.return_value = execute_result
    mock_session.delete = AsyncMock()
    mock_session.flush = AsyncMock()

    with patch("app.teams.service.get_team_member", return_value=owner_member):
        result = await remove_member(mock_session, team_id, owner_id)

    assert result is True


@pytest.mark.asyncio
async def test_invite_code_uses_secrets_token_urlsafe() -> None:
    """D-04: create_team использует secrets.token_urlsafe для генерации invite_code."""
    mock_session = AsyncMock()
    added_objects: list[object] = []

    def capture_add(obj: object) -> None:
        added_objects.append(obj)

    mock_session.add = capture_add

    generated_token = "mock_token_abc123"

    async def mock_flush() -> None:
        if added_objects and hasattr(added_objects[0], "invite_code"):
            added_objects[0].id = uuid.uuid4()

    mock_session.flush = mock_flush

    with patch(
        "app.teams.service.secrets.token_urlsafe", return_value=generated_token
    ) as mock_token:
        team = await create_team(mock_session, "Gamma Team", uuid.uuid4())
        mock_token.assert_called_once_with(32)

    assert team.invite_code == generated_token


# TASK-тесты, которые будут реализованы в плане 03-03
def test_assignee_membership() -> None:
    """TASK-02: assignee должен быть членом команды; нечлен → 422."""
    try:
        import app.tasks.service  # noqa: F401, PLC0415
    except (ModuleNotFoundError, ImportError):
        pytest.skip("app.tasks.service not yet implemented")
    pytest.fail("test_assignee_membership not implemented")


def test_deadline_tz() -> None:
    """TASK-03: deadline сохраняется timezone-aware; None допустим."""
    try:
        import app.tasks.service  # noqa: F401, PLC0415
    except (ModuleNotFoundError, ImportError):
        pytest.skip("app.tasks.service not yet implemented")
    pytest.fail("test_deadline_tz not implemented")


def test_status_transitions() -> None:
    """TASK-04: open→done = 422; open→in_progress = ok; done→in_progress = ok."""
    try:
        import app.tasks.service  # noqa: F401, PLC0415
    except (ModuleNotFoundError, ImportError):
        pytest.skip("app.tasks.service not yet implemented")
    pytest.fail("test_status_transitions not implemented")
