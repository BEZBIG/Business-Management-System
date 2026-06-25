"""Тесты Redis pub/sub listener (RT-01d, SC-2 routing).

Проверяют: доставку pmessage → send_to_user, пропуск служебных сообщений,
устойчивость к битому JSON, и graceful cancel (CancelledError raise).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_LISTENER_AVAILABLE = False

try:
    from app.realtime.listener import redis_pubsub_listener
    from app.realtime.manager import ConnectionManager

    _LISTENER_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    pass


def _make_pubsub_mock(messages: list[dict[str, Any]]) -> MagicMock:
    """Создаёт мок pubsub с заданной последовательностью сообщений.

    pubsub_redis.pubsub() — синхронный в redis-py (возвращает PubSub объект),
    а `async with pubsub` — асинхронный контекстный менеджер для закрытия соединений.
    """

    async def _listen() -> AsyncGenerator[dict[str, Any], None]:
        """Async-генератор заданных сообщений."""
        for msg in messages:
            yield msg

    mock_pubsub = MagicMock()
    mock_pubsub.psubscribe = AsyncMock(return_value=None)
    mock_pubsub.listen.return_value = _listen()
    mock_pubsub.__aenter__ = AsyncMock(return_value=mock_pubsub)
    mock_pubsub.__aexit__ = AsyncMock(return_value=False)

    # pubsub() — синхронный метод в redis-py → MagicMock, не AsyncMock
    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    return mock_redis


@pytest.mark.asyncio
async def test_listener_graceful_cancel() -> None:
    """RT-01d: отмена listener-таска (CancelledError) пробрасывается (graceful shutdown)."""
    if not _LISTENER_AVAILABLE:
        pytest.skip("app.realtime.listener not yet implemented")

    # Бесконечный генератор — блокируется ожидая следующее сообщение
    async def _infinite_listen() -> AsyncGenerator[dict[str, Any], None]:
        """Имитирует ожидание сообщения (будет отменён через task.cancel())."""
        await asyncio.sleep(1000)
        yield {}  # недостижимо

    # pubsub() — синхронный метод в redis-py → MagicMock
    mock_pubsub = MagicMock()
    mock_pubsub.psubscribe = AsyncMock(return_value=None)
    mock_pubsub.listen.return_value = _infinite_listen()
    mock_pubsub.__aenter__ = AsyncMock(return_value=mock_pubsub)
    mock_pubsub.__aexit__ = AsyncMock(return_value=False)

    mock_redis = MagicMock()
    mock_redis.pubsub.return_value = mock_pubsub
    mock_manager = AsyncMock(spec=ConnectionManager)

    task = asyncio.create_task(redis_pubsub_listener(mock_redis, mock_manager))

    # Даём таску запуститься
    await asyncio.sleep(0)

    # Отменяем таск — listener должен пробросить CancelledError
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_listener_routes_pmessage() -> None:
    """SC-2 (unit routing): pmessage → send_to_user с распарсенным user_id и payload."""
    if not _LISTENER_AVAILABLE:
        pytest.skip("app.realtime.listener not yet implemented")

    user_id = "test-user-abc"
    payload_data = {"type": "digest", "v": 1, "data": {"content": "тест"}}
    raw_data = json.dumps(payload_data)

    mock_redis = _make_pubsub_mock(
        [
            {
                "type": "pmessage",
                "pattern": "notifications:*",
                "channel": f"notifications:{user_id}",
                "data": raw_data,
            }
        ]
    )

    mock_manager = AsyncMock(spec=ConnectionManager)

    await redis_pubsub_listener(mock_redis, mock_manager)

    # Проверяем что send_to_user вызван с правильными аргументами
    mock_manager.send_to_user.assert_called_once_with(user_id, payload_data)


@pytest.mark.asyncio
async def test_listener_skips_non_pmessage() -> None:
    """Служебные сообщения (type != pmessage) пропускаются, send_to_user не вызывается."""
    if not _LISTENER_AVAILABLE:
        pytest.skip("app.realtime.listener not yet implemented")

    mock_redis = _make_pubsub_mock(
        [
            {
                "type": "psubscribe",
                "pattern": "notifications:*",
                "channel": "notifications:*",
                "data": 1,
            },
            {
                "type": "ping",
                "pattern": None,
                "channel": None,
                "data": None,
            },
        ]
    )

    mock_manager = AsyncMock(spec=ConnectionManager)

    await redis_pubsub_listener(mock_redis, mock_manager)

    # Служебные сообщения не должны триггерить доставку
    mock_manager.send_to_user.assert_not_called()


@pytest.mark.asyncio
async def test_listener_survives_invalid_json() -> None:
    """T-05-09: невалидный JSON в data → logger.warning + continue, листенер не падает."""
    if not _LISTENER_AVAILABLE:
        pytest.skip("app.realtime.listener not yet implemented")

    user_id = "bad-json-user"
    valid_user_id = "good-json-user"
    valid_payload = {"type": "digest", "v": 1}

    mock_redis = _make_pubsub_mock(
        [
            # Первое сообщение — битый JSON
            {
                "type": "pmessage",
                "pattern": "notifications:*",
                "channel": f"notifications:{user_id}",
                "data": "not valid json {{{",
            },
            # Второе сообщение — валидный JSON; listener должен продолжить и доставить
            {
                "type": "pmessage",
                "pattern": "notifications:*",
                "channel": f"notifications:{valid_user_id}",
                "data": json.dumps(valid_payload),
            },
        ]
    )

    mock_manager = AsyncMock(spec=ConnectionManager)

    # Не должен бросать исключений
    await redis_pubsub_listener(mock_redis, mock_manager)

    # Валидное сообщение должно быть доставлено
    mock_manager.send_to_user.assert_called_once_with(valid_user_id, valid_payload)


@pytest.mark.asyncio
async def test_listener_multiple_messages() -> None:
    """Listener корректно доставляет несколько pmessage подряд."""
    if not _LISTENER_AVAILABLE:
        pytest.skip("app.realtime.listener not yet implemented")

    messages = [
        {
            "type": "pmessage",
            "pattern": "notifications:*",
            "channel": f"notifications:user-{i}",
            "data": json.dumps({"type": "digest", "v": 1, "idx": i}),
        }
        for i in range(3)
    ]

    mock_redis = _make_pubsub_mock(messages)
    mock_manager = AsyncMock(spec=ConnectionManager)

    await redis_pubsub_listener(mock_redis, mock_manager)

    assert mock_manager.send_to_user.call_count == 3
    for i in range(3):
        mock_manager.send_to_user.assert_any_call(f"user-{i}", {"type": "digest", "v": 1, "idx": i})


@pytest.mark.asyncio
async def test_listener_reconnects_after_redis_error() -> None:
    """CR-02: RedisError не убивает listener-таск — происходит переподключение с backoff.

    Мок: первый вызов pubsub() поднимает RedisError (имитирует разрыв соединения),
    второй вызов возвращает нормальный pubsub с одним pmessage, затем CancelledError
    завершает таск — проверяем, что первая ошибка не убила цикл.
    """
    if not _LISTENER_AVAILABLE:
        pytest.skip("app.realtime.listener not yet implemented")

    from redis.exceptions import ConnectionError as RedisConnectionError

    user_id = "reconnect-test-user"
    payload_data = {"type": "digest", "v": 1}
    raw_data = json.dumps(payload_data)

    # Успешный pubsub после переподключения
    async def _listen_once() -> AsyncGenerator[dict[str, Any], None]:
        yield {
            "type": "pmessage",
            "pattern": "notifications:*",
            "channel": f"notifications:{user_id}",
            "data": raw_data,
        }
        # После единственного сообщения блокируемся — ждём CancelledError
        await asyncio.sleep(1000)

    # Первый pubsub выбрасывает ошибку при psubscribe
    fail_pubsub = MagicMock()
    fail_pubsub.psubscribe = AsyncMock(side_effect=RedisConnectionError("connection refused"))
    fail_pubsub.__aenter__ = AsyncMock(return_value=fail_pubsub)
    fail_pubsub.__aexit__ = AsyncMock(return_value=False)

    # Второй pubsub работает нормально
    ok_pubsub = MagicMock()
    ok_pubsub.psubscribe = AsyncMock(return_value=None)
    ok_pubsub.listen.return_value = _listen_once()
    ok_pubsub.__aenter__ = AsyncMock(return_value=ok_pubsub)
    ok_pubsub.__aexit__ = AsyncMock(return_value=False)

    mock_redis = MagicMock()
    mock_redis.pubsub.side_effect = [fail_pubsub, ok_pubsub]

    mock_manager = AsyncMock(spec=ConnectionManager)

    # _BACKOFF_INITIAL=0 → backoff-сон мгновенный. НЕ мокаем asyncio.sleep:
    # это глобальный объект модуля, и его патч сломал бы собственные await asyncio.sleep(0)
    # теста (event loop перестал бы уступать управление listener-таску).
    with patch("app.realtime.listener._BACKOFF_INITIAL", 0.0):
        task = asyncio.create_task(redis_pubsub_listener(mock_redis, mock_manager))
        # Ждём (с ограничением) пока listener переподключится и доставит сообщение
        for _ in range(100):
            await asyncio.sleep(0)
            if mock_manager.send_to_user.called:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    # Сообщение из второго подключения должно было доставиться
    mock_manager.send_to_user.assert_called_once_with(user_id, payload_data)
