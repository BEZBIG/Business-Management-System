"""Фикстуры pytest для realtime-тестов: mock_redis_jti, mock_pubsub, ws_token, _make_user."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest

_REALTIME_AVAILABLE: bool = False

try:
    from app.auth.models import User, UserRole  # noqa: PLC0415
    from app.auth.security import create_access_token  # noqa: PLC0415

    _REALTIME_AVAILABLE = True
except (ModuleNotFoundError, ImportError, Exception):
    pass


def _make_user(
    role: "UserRole | None" = None,
    user_id: uuid.UUID | None = None,
) -> "User":
    """Создаёт User без сохранения в БД (обходит SA relationship-инициализацию)."""
    if not _REALTIME_AVAILABLE:
        raise RuntimeError("app.auth not available")  # noqa: TRY003

    if role is None:
        role = UserRole.USER
    u = User.__new__(User)
    u.__dict__.update({
        "id": user_id or uuid.uuid4(),
        "email": "realtime-test@example.com",
        "password_hash": "h",
        "role": role,
        "is_active": True,
    })
    return u


@pytest.fixture
def mock_redis_jti() -> AsyncMock:
    """Мок Redis для jti-blacklist: exists() всегда 0 (токен не отозван)."""
    mock = AsyncMock()
    mock.exists.return_value = 0
    mock.set.return_value = True
    return mock


@pytest.fixture
def mock_pubsub() -> AsyncMock:
    """Мок Redis pub/sub с предзаполненной очередью тестовых pmessage-словарей."""

    async def _listen() -> AsyncGenerator[dict[str, Any], None]:
        """Возвращает один тестовый pmessage, затем завершается."""
        yield {
            "type": "pmessage",
            "pattern": "notifications:*",
            "channel": "notifications:test-user-id",
            "data": '{"type":"digest","v":1,"ts":"2026-06-25T07:00:00Z","data":{"content":"тест","generated_at":"2026-06-25T07:00:00Z"}}',
        }

    mock = AsyncMock()
    mock.listen.return_value = _listen()
    return mock


@pytest.fixture
def ws_token() -> str:
    """JWT access-токен для WebSocket subprotocol тестов."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.auth not yet implemented")
    return create_access_token(str(uuid.uuid4()), "user")
