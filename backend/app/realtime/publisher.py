"""Хелпер публикации real-time событий в Redis pub/sub-канал уведомлений.

Функция publish_event сериализует событие через Pydantic и публикует
в per-user канал notifications:{user_id} обычной командой redis.publish
(не pub/sub-коннект; D-07, D-09).
"""

from __future__ import annotations

import structlog
from redis.asyncio import Redis

from app.realtime.schemas import RealtimeEvent

logger = structlog.get_logger(__name__)


async def publish_event(redis: Redis, user_id: str, event: RealtimeEvent) -> None:
    """Публикует real-time событие в Redis-канал уведомлений пользователя.

    Канал формируется как notifications:{user_id} — per-user пространство имён (D-07).
    Полезная нагрузка — event.model_dump_json(): ISO-8601 datetime, UUID как str.
    Использует обычную команду publish, НЕ pub/sub-коннект (D-09).

    Аргументы:
        redis:   синглтон redis_client (или любой async Redis-клиент для тестов)
        user_id: идентификатор получателя; канал будет notifications:{user_id}
        event:   экземпляр одного из типов RealtimeEvent (discriminated union D-10)
    """
    channel = f"notifications:{user_id}"
    payload = event.model_dump_json()
    await redis.publish(channel, payload)
    logger.info("realtime_publish", channel=channel, event_type=event.type)
