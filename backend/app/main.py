"""Точка входа FastAPI-приложения: создаёт app, настраивает метрики, middleware и роутеры."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.core.logging import setup_logging

setup_logging()

from app.admin.setup import setup_admin  # noqa: E402
from app.auth.router import router as auth_router  # noqa: E402
from app.auth.router import users_router  # noqa: E402
from app.auth.service import seed_first_superuser  # noqa: E402
from app.core.broker import broker  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.middleware import RequestIDMiddleware  # noqa: E402
from app.core.redis_client import redis_client  # noqa: E402
from app.db.engine import async_session_factory, engine  # noqa: E402
from app.health.router import router as health_router  # noqa: E402
from app.meetings.router import calendar_router  # noqa: E402
from app.meetings.router import router as meetings_router  # noqa: E402
from app.metrics.setup import setup_metrics  # noqa: E402
from app.ratings.router import router as ratings_router  # noqa: E402
from app.ratings.router import users_ratings_router  # noqa: E402
from app.realtime.listener import redis_pubsub_listener  # noqa: E402
from app.realtime.manager import manager  # noqa: E402
from app.realtime.router import router as realtime_router  # noqa: E402
from app.tasks.router import router as tasks_router  # noqa: E402
from app.teams.router import router as teams_router  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет запуском и остановкой async-подключений: брокер, Redis, пул БД, pub/sub listener.

    После старта брокера идемпотентно создаёт первого admin из env.
    Запускает per-worker Redis pub/sub listener на отдельном коннекте (D-08, D-09, T-05-12).
    """
    await broker.start()

    async with async_session_factory() as session:
        await seed_first_superuser(session)
        await session.commit()

    # Отдельный pub/sub-коннект — не переиспользует синглтон redis_client (D-09, T-05-13)
    pubsub_redis = Redis.from_url(settings.redis_url, decode_responses=True)
    # Один таск на воркер — per-worker backplane (D-08)
    listener_task = asyncio.create_task(redis_pubsub_listener(pubsub_redis, manager))

    yield

    # Graceful shutdown: сначала listener, затем брокер/redis/engine (T-05-12, CR-03).
    # Перехватываем любое исключение из listener_task: CancelledError — нормальная остановка,
    # остальное — listener умер раньше shutdown (уже залогировано asyncio).
    # Все шаги cleanup выполняются безусловно — утечки соединений при rolling deploy исключены.
    listener_task.cancel()
    try:
        await listener_task
    except (asyncio.CancelledError, Exception):
        pass
    await pubsub_redis.aclose()

    await broker.stop()
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(
    title="TeamFlow",
    description="Business Management System — async FastAPI backend",
    version="0.1.0",
    lifespan=lifespan,
)

setup_metrics(app)

app.add_middleware(RequestIDMiddleware)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(teams_router)
app.include_router(tasks_router)
app.include_router(meetings_router)
app.include_router(calendar_router)
app.include_router(ratings_router)
app.include_router(users_ratings_router)
app.include_router(realtime_router)

setup_admin(app, engine)
