"""
TeamFlow FastAPI application entry point.

Startup order is critical:
  1. setup_logging()        — structlog JSON, must be first so all imports emit JSON logs.
  2. app = FastAPI(lifespan) — FastAPI app with async lifespan context manager.
  3. setup_metrics(app)     — Prometheus Instrumentator BEFORE any middleware (Pitfall 5).
  4. add_middleware(...)    — RequestIDMiddleware after metrics to avoid missing http_ labels.
  5. include_router(...)    — domain routers.

Lifespan manages the connection lifecycle for all three external services:
  - RabbitMQ via broker.start() / broker.stop()  (connect_robust + fail_fast=False, D-14)
  - Redis is ready immediately (Redis.from_url is lazy; no explicit start needed)
  - SQLAlchemy engine is disposed on shutdown to release pooled connections cleanly

Entry point for ASGI server:
  uvicorn app.main:app --reload    (dev)
  gunicorn -k uvicorn.workers.UvicornWorker app.main:app  (prod)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import setup_logging

# Setup structured logging first — must precede all other imports that log
setup_logging()

from app.core.broker import broker  # noqa: E402  (after setup_logging)
from app.core.middleware import RequestIDMiddleware  # noqa: E402
from app.core.redis_client import redis_client  # noqa: E402
from app.db.engine import engine  # noqa: E402
from app.health.router import router as health_router  # noqa: E402
from app.metrics.setup import setup_metrics  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of all async connections.

    Startup:
      - broker.start()   — establishes AMQP connection via connect_robust (Pattern 6).
                           fail_fast=False means startup continues even if RabbitMQ is
                           temporarily unavailable; reconnect runs in the background.

    Shutdown:
      - broker.stop()    — gracefully closes AMQP channels and connection.
      - redis_client.aclose() — releases Redis connection pool.
      - engine.dispose() — closes all SQLAlchemy pool connections to PostgreSQL.
    """
    # --- Startup ---
    await broker.start()
    # redis_client is ready immediately (Redis.from_url is lazy — no explicit connect)

    yield

    # --- Shutdown ---
    await broker.stop()
    await redis_client.aclose()
    await engine.dispose()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TeamFlow",
    description="Business Management System — async FastAPI backend",
    version="0.1.0",
    lifespan=lifespan,
)

# Step 3: Prometheus metrics BEFORE middleware (Pitfall 5 — order is mandatory)
setup_metrics(app)

# Step 4: Middleware
app.add_middleware(RequestIDMiddleware)

# Step 5: Routers
app.include_router(health_router)
