"""
Health check endpoints (D-07, D-08, NFR-01 criterion #1).

Two separate probes with different semantics:

  GET /health/live  — liveness probe: process is alive, no I/O whatsoever (D-07).
                      Used by Kubernetes/Docker to decide whether to restart the container.

  GET /health/ready — readiness probe: deep check of all three dependencies (D-08).
                      Returns 200 only when PostgreSQL + Redis + RabbitMQ are all reachable.
                      Returns 503 (not 200) when any dependency is unavailable — this is the
                      correct signal to a load balancer to stop routing traffic to this instance.

Security notes (T-03-01):
  - Response bodies expose ONLY "ok"/"error" per service — never DSNs, hostnames, or versions.
  - No internal topology is revealed in the JSON payload.
"""

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
    """Liveness probe — returns 200 immediately with no I/O (D-07).

    Never accesses PostgreSQL, Redis, or RabbitMQ.  If this endpoint returns
    anything other than 200 the process itself is broken.
    """
    return {"status": "ok"}


@router.get("/ready")
async def readiness(
    session: AsyncSession = Depends(get_async_session),
) -> JSONResponse:
    """Readiness probe — pings all three dependencies (D-08, criterion #1).

    Returns:
      200 + {"status": "ok",       "services": {...}} — all dependencies reachable.
      503 + {"status": "degraded", "services": {...}} — at least one dependency is down.

    Secure behaviour (T-03-01): response contains only "ok"/"error" per service.
    DSNs, host names, error messages, and versions are NOT included in the response.
    """
    checks: dict[str, str] = {}

    # --- PostgreSQL ---
    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"

    # --- Redis ---
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    # --- RabbitMQ (via broker connection state) ---
    try:
        if broker.connection is not None and not broker.connection.is_closed:
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
