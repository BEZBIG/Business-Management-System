"""Async-клиент Redis через redis.asyncio (redis-py 7+).

Используется пространство redis.asyncio (не aioredis); decode_responses=True — значения как str.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
