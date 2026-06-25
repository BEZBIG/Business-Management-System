"""Фоновый Redis pub/sub listener: psubscribe notifications:* → доставка локальным соединениям.

Один экземпляр на воркер (per-worker). Запускается в lifespan в плане 05-03.
decode_responses=True на pubsub_redis → channel и data как str (Pitfall 2).

Устойчивость к разрыву соединения (CR-02, WR-03):
  - Цикл while True с экспоненциальным backoff (1s → 30s) при RedisError / OSError.
  - CancelledError пробрасывается — обеспечивает graceful shutdown (Pitfall 5).
  - После успешного переподключения backoff сбрасывается до 1s.
"""

from __future__ import annotations

import asyncio
import json

import structlog
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

from app.realtime.manager import ConnectionManager

logger = structlog.get_logger(__name__)

_BACKOFF_INITIAL = 1.0
_BACKOFF_MAX = 30.0


async def redis_pubsub_listener(
    pubsub_redis: Redis,
    manager: ConnectionManager,
) -> None:
    """Фоновый таск: psubscribe notifications:* → доставка сообщений локальным соединениям.

    Подписывается на паттерн notifications:* (D-07), парсит user_id из имени канала
    (notifications:{user_id}), декодирует JSON-данные и вызывает manager.send_to_user.

    Обработка ошибок:
    - asyncio.CancelledError → пробрасывается (raise) для graceful shutdown (D-09, Pitfall 5)
    - RedisError / ConnectionError / OSError → logger.warning + backoff + переподписка (CR-02)
    - json.JSONDecodeError → logger.warning + continue (RT-01 устойчивость, T-05-09)
    - Служебные сообщения psubscribe-подтверждений (type != "pmessage") → пропускаются

    Цикл `async for ... in pubsub.listen()` — async-генератор, не get_message(timeout=0):
    блокируется до следующего сообщения, отдаёт управление event loop (Pitfall 1).
    """
    backoff = _BACKOFF_INITIAL
    while True:
        try:
            async with pubsub_redis.pubsub() as pubsub:
                await pubsub.psubscribe("notifications:*")
                logger.info("pubsub_listener_started", pattern="notifications:*")
                # Успешное подключение — сбрасываем backoff
                backoff = _BACKOFF_INITIAL

                async for message in pubsub.listen():
                    # Пропускаем служебные сообщения (psubscribe-подтверждения, ping и т.п.)
                    if message["type"] != "pmessage":
                        continue

                    channel: str = message["channel"]  # "notifications:{user_id}"
                    user_id = channel.split(":", 1)[1]
                    raw_data: str = message["data"]

                    # Защита от битого JSON — не роняем таск (T-05-09, V5 Input Validation)
                    try:
                        payload = json.loads(raw_data)
                    except json.JSONDecodeError:
                        logger.warning("pubsub_invalid_json", channel=channel, raw=raw_data[:200])
                        continue

                    await manager.send_to_user(user_id, payload)

                # listen() завершился штатно (генератор исчерпан / pubsub закрыт):
                # в проде это происходит только при намеренном закрытии — выходим,
                # реконнект делаем лишь при RedisError/OSError ниже (иначе busy-loop).
                return

        except asyncio.CancelledError:
            # Нормальная остановка при shutdown — обязательно пробрасываем (Pitfall 5)
            logger.info("pubsub_listener_stopping")
            raise
        except (RedisConnectionError, RedisError, OSError) as exc:
            # Потеря соединения с Redis — повторная подписка с backoff (CR-02, WR-03)
            logger.warning(
                "pubsub_listener_redis_error",
                error=str(exc),
                retry_in=backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _BACKOFF_MAX)
