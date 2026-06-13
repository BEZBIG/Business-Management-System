"""
Async Redis client via redis.asyncio (redis-py 7+/8+).

Uses redis.asyncio namespace — NOT standalone aioredis (forbidden by project docs §"What NOT to Use").
decode_responses=True: all values are returned as str (not bytes); convenient for
session tokens, pub/sub payloads, and rate-limit counters.

Exported singleton:
  redis_client — used in /health/ready ping check and closed in lifespan shutdown.
"""

from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings

redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
