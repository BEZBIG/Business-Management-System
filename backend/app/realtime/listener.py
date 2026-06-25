"""Фоновый Redis pub/sub listener: psubscribe notifications:* → доставка локальным соединениям.

Один экземпляр на воркер (per-worker). Запускается в lifespan в плане 05-03.
decode_responses=True на pubsub_redis → channel и data как str (Pitfall 2).
"""

from __future__ import annotations

import asyncio
import json

import structlog
from redis.asyncio import Redis

from app.realtime.manager import ConnectionManager

logger = structlog.get_logger(__name__)


async def redis_pubsub_listener(
    pubsub_redis: Redis,
    manager: ConnectionManager,
) -> None:
    """Фоновый таск: psubscribe notifications:* → доставка сообщений локальным соединениям.

    Подписывается на паттерн notifications:* (D-07), парсит user_id из имени канала
    (notifications:{user_id}), декодирует JSON-данные и вызывает manager.send_to_user.

    Обработка ошибок:
    - asyncio.CancelledError → пробрасывается (raise) для graceful shutdown (D-09, Pitfall 5)
    - json.JSONDecodeError → logger.warning + continue (RT-01 устойчивость, T-05-09)
    - Служебные сообщения psubscribe-подтверждений (type != "pmessage") → пропускаются

    Цикл `async for ... in pubsub.listen()` — async-генератор, не get_message(timeout=0):
    блокируется до следующего сообщения, отдаёт управление event loop (Pitfall 1).
    """
    async with pubsub_redis.pubsub() as pubsub:
        await pubsub.psubscribe("notifications:*")
        logger.info("pubsub_listener_started", pattern="notifications:*")

        try:
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

        except asyncio.CancelledError:
            # Нормальная остановка при shutdown — обязательно пробрасываем (Pitfall 5)
            logger.info("pubsub_listener_stopping")
            raise
