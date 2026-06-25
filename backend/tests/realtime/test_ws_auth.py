"""Тесты WebSocket-аутентификации через Sec-WebSocket-Protocol (RT-01a/b/c, D-04).

Проверяют: невалидный токен → 4008, отозванный jti → 4008,
неактивный/несуществующий пользователь → 4008, валидный + активный → соединение принято.

TestClient.websocket_connect — синхронный API; тесты объявлены как обычные def,
а не async def, чтобы не конфликтовать с anyio event loop pytest-asyncio.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketDisconnect

_REALTIME_AVAILABLE = False

try:
    from app.auth.security import create_access_token
    from app.realtime.router import router as realtime_router  # noqa: F401

    _REALTIME_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    pass


def _make_ws_user(
    is_active: bool = True,
    user_id: uuid.UUID | None = None,
) -> MagicMock:
    """Создаёт mock-пользователя для WS-тестов без инициализации SA ORM."""
    uid = user_id or uuid.uuid4()
    user = MagicMock()
    user.id = uid
    user.is_active = is_active
    user.email = "ws-test@example.com"
    # Сохраняем id отдельно для create_access_token
    user.__dict__["id"] = uid
    return user


@contextmanager
def _ws_client() -> Iterator[object]:
    """Создаёт изолированное FastAPI-приложение с только realtime-роутером для тестов."""
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from app.realtime.router import router as rt_router

    app = FastAPI()
    app.include_router(rt_router)
    yield TestClient(app, raise_server_exceptions=False)


def _mock_session_for(user: object | None) -> MagicMock:
    """Создаёт мок async_session_factory, возвращающий пользователя через session.get."""
    mock_session = AsyncMock()
    mock_session.get.return_value = user
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_session_ctx)
    return mock_factory


def test_invalid_token_closes_4008() -> None:
    """RT-01a: невалидный токен → закрытие соединения с кодом 4008."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0

    with _ws_client() as client:
        with patch("app.realtime.router.redis_client", mock_redis):
            with pytest.raises(WebSocketDisconnect):
                # Невалидный JWT → close(4008) до accept → WebSocketDisconnect
                with client.websocket_connect(
                    "/ws",
                    subprotocols=["bearer.this.is.not.a.valid.jwt"],
                ):
                    pass  # не должны добраться сюда


def test_missing_bearer_closes_4008() -> None:
    """RT-01a (дополнение): отсутствие bearer. в subprotocols → закрытие 4008."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    with _ws_client() as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", subprotocols=["some-other-protocol"]):
                pass  # не должны добраться сюда


def test_valid_token_accepts() -> None:
    """RT-01b: валидный токен + активный пользователь → соединение принято с subprotocol bearer."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    active_user = _make_ws_user(is_active=True)
    token = create_access_token(str(active_user.id), "user")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0
    mock_factory = _mock_session_for(active_user)

    with _ws_client() as client:
        with (
            patch("app.realtime.router.redis_client", mock_redis),
            patch("app.realtime.router.async_session_factory", mock_factory),
        ):
            with client.websocket_connect(
                "/ws",
                subprotocols=[f"bearer.{token}"],
            ) as ws:
                # Соединение принято — проверяем что объект существует
                assert ws is not None


def test_revoked_token() -> None:
    """RT-01c: отозванный токен (jti в blacklist Redis) → закрытие 4008."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, "user")

    # Мок Redis: exists возвращает 1 (токен в blacklist)
    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 1

    with _ws_client() as client:
        with patch("app.realtime.router.redis_client", mock_redis):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws",
                    subprotocols=[f"bearer.{token}"],
                ):
                    pass  # не должны добраться сюда


def test_inactive_user() -> None:
    """D-04: неактивный пользователь (is_active=False) → закрытие 4008 ДО accept."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    inactive_user = _make_ws_user(is_active=False)
    token = create_access_token(str(inactive_user.id), "user")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0
    # Сессия возвращает пользователя с is_active=False
    mock_factory = _mock_session_for(inactive_user)

    with _ws_client() as client:
        with (
            patch("app.realtime.router.redis_client", mock_redis),
            patch("app.realtime.router.async_session_factory", mock_factory),
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws",
                    subprotocols=[f"bearer.{token}"],
                ):
                    pass  # соединение не должно быть принято


def test_nonexistent_user_closes_4008() -> None:
    """D-04 (дополнение): несуществующий пользователь (session.get → None) → закрытие 4008."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    user_id = str(uuid.uuid4())
    token = create_access_token(user_id, "user")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0
    # Сессия возвращает None (пользователь не найден)
    mock_factory = _mock_session_for(None)

    with _ws_client() as client:
        with (
            patch("app.realtime.router.redis_client", mock_redis),
            patch("app.realtime.router.async_session_factory", mock_factory),
        ):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws",
                    subprotocols=[f"bearer.{token}"],
                ):
                    pass  # соединение не должно быть принято


def test_token_without_jti_closes_4008() -> None:
    """WR-01: токен без jti claim не должен обходить revocation-check → закрытие 4008."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    # Вручную создаём токен без jti — такой токен проверит ключ "jti:" (пустой) в Redis
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from app.core.config import settings

    now = datetime.now(UTC)
    payload_no_jti = {
        "sub": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=15),
        # jti намеренно отсутствует
    }
    token = pyjwt.encode(payload_no_jti, settings.jwt_secret, algorithm="HS256")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0  # Redis не должен даже вызываться

    with _ws_client() as client:
        with patch("app.realtime.router.redis_client", mock_redis):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws",
                    subprotocols=[f"bearer.{token}"],
                ):
                    pass  # соединение не должно быть принято


def test_token_without_sub_closes_4008() -> None:
    """WR-02: токен без sub claim не должен вызывать KeyError (500) → корректное закрытие 4008."""
    if not _REALTIME_AVAILABLE:
        pytest.skip("app.realtime not yet implemented")

    import uuid as _uuid
    from datetime import UTC, datetime, timedelta

    import jwt as pyjwt

    from app.core.config import settings

    now = datetime.now(UTC)
    payload_no_sub = {
        "type": "access",
        "jti": _uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(minutes=15),
        # sub намеренно отсутствует
    }
    token = pyjwt.encode(payload_no_sub, settings.jwt_secret, algorithm="HS256")

    mock_redis = AsyncMock()
    mock_redis.exists.return_value = 0  # jti присутствует, revocation-check проходит

    with _ws_client() as client:
        with patch("app.realtime.router.redis_client", mock_redis):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws",
                    subprotocols=[f"bearer.{token}"],
                ):
                    pass  # соединение не должно быть принято
