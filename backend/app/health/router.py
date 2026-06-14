"""Эндпоинты проверки здоровья: liveness без I/O и readiness с пингом зависимостей."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.broker import broker
from app.core.redis_client import redis_client
from app.db.session import get_async_session

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Liveness-проба: сразу возвращает 200 без обращения к зависимостям."""
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> JSONResponse:
    """Readiness-проба: пингует PostgreSQL, Redis и RabbitMQ; 200 если все доступны, иначе 503."""
    checks: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"

    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    try:
        if await broker.ping(timeout=2.0):
            checks["rabbitmq"] = "ok"
        else:
            checks["rabbitmq"] = "error"
    except Exception:
        checks["rabbitmq"] = "error"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        content={
            "status": "ok" if all_ok else "degraded",
            "services": checks,
        },
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
    )
