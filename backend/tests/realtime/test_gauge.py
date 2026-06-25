"""Тест Prometheus gauge (RT-03b): проверка отсутствия дрейфа при disconnect.

Gauge инкрементируется после accept и декрементируется в try/finally — гарантия D-12.
TestClient.websocket_connect — синхронный API; тест объявлен как обычный def.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_GAUGE_AVAILABLE = False

try:
    from app.auth.security import create_access_token
    from app.realtime.manager import WS_CONNECTIONS
    from app.realtime.router import router as realtime_router  # noqa: F401

    _GAUGE_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    pass


def _make_gauge_user(is_active: bool = True) -> MagicMock:
    """Создаёт mock-пользователя для gauge-тестов без инициализации SA ORM."""
    uid = uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.is_active = is_active
    user.email = "gauge-test@example.com"
    return user


@contextmanager
def _ws_client_gauge() -> Iterator[object]:
    """Создаёт изолированное FastAPI-приложение для gauge-тестов."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from app.realtime.router import router as rt_router

    app = FastAPI()
    app.include_router(rt_router)
    yield TestClient(app, raise_server_exceptions=False)


def _mock_factory_for(user: object | None) -> MagicMock:
    """Создаёт мок async_session_factory для gauge-тестов."""
    mock_session = AsyncMock()
    mock_session.get.return_value = user
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_session_ctx)
    return mock_factory


def test_gauge_no_drift_on_disconnect() -> None:
    """RT-03b: gauge инкрементится при подключении и декрементится при разрыве соединения."""
    if not _GAUGE_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    active_user = _make_gauge_user(is_active=True)
    token = create_access_token(str(active_user.id), "user")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0
    mock_factory = _mock_factory_for(active_user)

    # Фиксируем начальное значение gauge
    initial_value = WS_CONNECTIONS._value.get()  # noqa: SLF001

    with _ws_client_gauge() as client:
        with (
            patch("app.realtime.router.redis_client", mock_redis),
            patch("app.realtime.router.async_session_factory", mock_factory),
        ):
            # Открываем соединение — gauge должен вырасти
            with client.websocket_connect(
                "/ws",
                subprotocols=[f"bearer.{token}"],
            ):
                during_value = WS_CONNECTIONS._value.get()  # noqa: SLF001
                assert during_value == initial_value + 1, (
                    f"Gauge должен быть {initial_value + 1} при активном соединении, "
                    f"но равен {during_value}"
                )
            # После выхода из контекста — gauge должен вернуться к исходному значению

    after_value = WS_CONNECTIONS._value.get()  # noqa: SLF001
    assert after_value == initial_value, (
        f"Gauge должен вернуться к {initial_value} после disconnect, "
        f"но равен {after_value} (дрейф!)"
    )
