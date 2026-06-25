"""Тесты HTTP-роутера встреч и эндпоинта /calendar.

Unit-тесты используют DI-override и моки AsyncSession — без живой БД.
Интеграционные тесты помечены @pytest.mark.integration (требуют Docker-инфраструктуры).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

try:
    from app.auth.dependencies import get_current_user
    from app.auth.models import User, UserRole
    from app.auth.security import create_access_token
    from app.db.session import get_async_session
    from app.main import app
    from app.meetings.dependencies import require_meeting_owner
    from app.meetings.models import Meeting, MeetingStatus
    from app.meetings.schemas import CalendarEvent
    from app.teams.dependencies import get_team_membership
    from app.teams.models import TeamMember, TeamRole

    _MEETINGS_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _MEETINGS_AVAILABLE = False


def _make_user(role: UserRole | None = None, user_id: uuid.UUID | None = None) -> User:
    """Создаёт User без сохранения в БД."""
    if role is None:
        role = UserRole.USER
    u = User(email="t@example.com", password_hash="h", role=role, is_active=True)
    u.id = user_id or uuid.uuid4()
    return u


def _make_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    role: TeamRole | None = None,
) -> TeamMember:
    """Создаёт TeamMember без сохранения в БД."""
    if role is None:
        role = TeamRole.MEMBER
    m = TeamMember(team_id=team_id, user_id=user_id, role=role)
    m.created_at = datetime.now(UTC)
    return m


def _make_meeting(
    meeting_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    creator_id: uuid.UUID | None = None,
    participant_ids: list[uuid.UUID] | None = None,
) -> Meeting:
    """Создаёт Meeting без сохранения в БД."""
    tid = team_id or uuid.uuid4()
    cid = creator_id or uuid.uuid4()
    now = datetime.now(UTC)

    m = Meeting.__new__(Meeting)
    # Обходим SA relationship-инициализацию через прямую установку __dict__
    m.__dict__.update(
        {
            "id": meeting_id or uuid.uuid4(),
            "team_id": tid,
            "creator_id": cid,
            "title": "Test Meeting",
            "description": None,
            "status": MeetingStatus.ACTIVE,
            "start_time": now + timedelta(hours=1),
            "end_time": now + timedelta(hours=2),
            "jitsi_room_token": "test_token_abc123",
            "created_at": now,
        }
    )

    # Создаём участников (creator всегда включён)
    all_ids = list({cid, *(participant_ids or [])})
    participants = []
    for uid in all_ids:
        p = MagicMock()
        p.user_id = uid
        participants.append(p)
    # Устанавливаем participants напрямую в __dict__, минуя SA backref
    m.__dict__["participants"] = participants

    return m


# ---------------------------------------------------------------------------
# Unit-тесты (без живой БД — DI-override)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_meeting() -> None:
    """MEET-01: POST /meetings создаёт встречу; jitsi_url доступна только участнику."""
    if not _MEETINGS_AVAILABLE:
        pytest.skip("app.meetings not yet implemented")

    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    member = _make_member(team_id, user_id, TeamRole.MEMBER)
    meeting = _make_meeting(team_id=team_id, creator_id=user_id)

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    now = datetime.now(UTC)
    request_body = {
        "title": "Test Meeting",
        "start_time": (now + timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "participant_ids": [],
    }

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.meetings.router.create_meeting", return_value=meeting),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_team_membership] = lambda: member

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.post(f"/teams/{team_id}/meetings", json=request_body)
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["title"] == "Test Meeting"
    # creator является участником → jitsi_url должна быть заполнена
    assert body["jitsi_url"] is not None
    assert body["jitsi_url"].startswith("https://meet.jit.si/")


@pytest.mark.asyncio
async def test_create_meeting_jitsi_url_hidden_for_non_participant() -> None:
    """D-10: jitsi_url равна None для пользователя, не являющегося участником встречи."""
    if not _MEETINGS_AVAILABLE:
        pytest.skip("app.meetings not yet implemented")

    creator_id = uuid.uuid4()
    other_user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    # Встреча создана другим пользователем; other_user — не участник
    meeting = _make_meeting(team_id=team_id, creator_id=creator_id, participant_ids=[])

    other_user = _make_user(UserRole.USER, other_user_id)
    member = _make_member(team_id, other_user_id, TeamRole.MEMBER)
    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    now = datetime.now(UTC)
    request_body = {
        "title": "Test Meeting",
        "start_time": (now + timedelta(hours=1)).isoformat(),
        "end_time": (now + timedelta(hours=2)).isoformat(),
        "participant_ids": [],
    }

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.meetings.router.create_meeting", return_value=meeting),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: other_user
        app.dependency_overrides[get_team_membership] = lambda: member

        try:
            token = create_access_token(str(other_user_id), "user")
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {token}"},
            ) as ac:
                resp = await ac.post(f"/teams/{team_id}/meetings", json=request_body)
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 201, resp.text
    body = resp.json()
    # other_user не участник → jitsi_url должна быть None
    assert body["jitsi_url"] is None


@pytest.mark.asyncio
async def test_cancel_meeting_owner_only_403() -> None:
    """MEET-03: DELETE /meetings/{id}: участник без прав creator → 403."""
    if not _MEETINGS_AVAILABLE:
        pytest.skip("app.meetings not yet implemented")

    from fastapi import HTTPException

    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    meeting_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    member = _make_member(team_id, user_id, TeamRole.MEMBER)

    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    async def _raise_403() -> None:
        raise HTTPException(status_code=403, detail="Only meeting owner can perform this action")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with patch("app.auth.dependencies.redis_client", mock_redis):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_team_membership] = lambda: member
        app.dependency_overrides[require_meeting_owner] = _raise_403

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                resp = await ac.delete(f"/teams/{team_id}/meetings/{meeting_id}")
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_calendar_combined() -> None:
    """CAL-01: GET /calendar объединяет задачи и встречи с type-дискриминатором."""
    if not _MEETINGS_AVAILABLE:
        pytest.skip("app.meetings not yet implemented")

    user_id = uuid.uuid4()
    user = _make_user(UserRole.USER, user_id)
    mock_session = AsyncMock()

    async def _override_session() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    now = datetime.now(UTC)
    mock_events = [
        CalendarEvent(
            type="task",
            id=uuid.uuid4(),
            title="Задача дедлайн",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=1),
            is_point_event=True,
        ),
        CalendarEvent(
            type="meeting",
            id=uuid.uuid4(),
            title="Встреча",
            start=now + timedelta(hours=2),
            end=now + timedelta(hours=3),
        ),
    ]

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with (
        patch("app.auth.dependencies.redis_client", mock_redis),
        patch("app.meetings.router.get_calendar_events", return_value=mock_events),
    ):
        app.dependency_overrides[get_async_session] = _override_session
        app.dependency_overrides[get_current_user] = lambda: user

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": f"Bearer {create_access_token(str(user_id), 'user')}"},
            ) as ac:
                # params= экранирует автоматически; strftime без tzinfo —
                # FastAPI принимает naive datetime
                from_dt = now.strftime("%Y-%m-%dT%H:%M:%S")
                to_dt = (now + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
                resp = await ac.get(
                    "/calendar",
                    params={"from_dt": from_dt, "to_dt": to_dt, "view": "month"},
                )
        finally:
            app.dependency_overrides.clear()

    assert resp.status_code == 200, resp.text
    events = resp.json()
    assert len(events) == 2
    types = {e["type"] for e in events}
    assert "task" in types
    assert "meeting" in types


@pytest.mark.asyncio
async def test_require_meeting_owner_rejects_non_owner() -> None:
    """require_meeting_owner: участник без прав creator → 403 (D-03)."""
    if not _MEETINGS_AVAILABLE:
        pytest.skip("app.meetings not yet implemented")

    from fastapi import HTTPException

    from app.meetings.dependencies import require_meeting_owner

    user_id = uuid.uuid4()
    creator_id = uuid.uuid4()  # другой создатель
    team_id = uuid.uuid4()
    meeting = _make_meeting(team_id=team_id, creator_id=creator_id)
    user = _make_user(UserRole.USER, user_id)

    with pytest.raises(HTTPException) as exc_info:
        await require_meeting_owner(meeting=meeting, current_user=user)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_meeting_owner_allows_creator() -> None:
    """require_meeting_owner: creator встречи пропускается."""
    if not _MEETINGS_AVAILABLE:
        pytest.skip("app.meetings not yet implemented")

    from app.meetings.dependencies import require_meeting_owner

    user_id = uuid.uuid4()
    team_id = uuid.uuid4()
    meeting = _make_meeting(team_id=team_id, creator_id=user_id)
    user = _make_user(UserRole.USER, user_id)

    result = await require_meeting_owner(meeting=meeting, current_user=user)
    assert result is meeting
