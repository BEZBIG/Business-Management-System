"""Точка входа FastAPI-приложения: создаёт app, настраивает метрики, middleware и роутеры."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import setup_logging

setup_logging()

from app.core.broker import broker  # noqa: E402
from app.core.middleware import RequestIDMiddleware  # noqa: E402
from app.core.redis_client import redis_client  # noqa: E402
from app.db.engine import engine  # noqa: E402
from app.health.router import router as health_router  # noqa: E402
from app.metrics.setup import setup_metrics  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Управляет запуском и остановкой async-подключений: брокер, Redis, пул БД."""
    await broker.start()

    yield

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
