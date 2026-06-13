"""
pytest conftest for the TeamFlow backend test suite.

Fixtures provided:
  - anyio_backend   : force asyncio backend for pytest-asyncio
  - async_engine    : SQLAlchemy AsyncEngine with NullPool (safe for parallel fixtures)
  - client          : httpx AsyncClient backed by the FastAPI ASGI app

Design notes:
  - NullPool is used to avoid connection-pool state leaking between test functions
    (see RESEARCH.md Pitfall / Pattern 12).  Each test function gets a fresh
    connection; this is slightly slower but correct.
  - The `app` import is deferred inside the fixture so that `pytest --collect-only`
    succeeds even before Wave 2/3 create app/main.py.  Collection will succeed;
    the fixture itself will fail only when the test *runs*.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool


# ---------------------------------------------------------------------------
# Backend selection — must be "asyncio" so pytest-asyncio 1.4.0 picks it up
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Async engine with NullPool — safe for concurrent test fixtures (A1)
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create a temporary async engine bound to the test DATABASE_URL.

    Uses NullPool so no connections are held between test functions.
    The URL defaults to a throwaway in-memory or test database via the
    TEST_DATABASE_URL env var (falls back to DATABASE_URL).
    """
    url = os.environ.get(
        "TEST_DATABASE_URL",
        os.environ.get("DATABASE_URL", "postgresql+asyncpg://teamflow:teamflow@localhost/teamflow_test"),
    )
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# HTTP client backed by the ASGI app (deferred import so collection succeeds)
# ---------------------------------------------------------------------------

@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client for making requests to the FastAPI application.

    The `app` object is imported lazily so that test collection succeeds even
    before `app/main.py` is created in later plan waves.
    """
    try:
        from app.main import app  # noqa: PLC0415  (lazy import by design)
    except ImportError:
        pytest.skip("app.main not yet implemented (Wave 2+)")
        return

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Dependency mocks for /health/ready readiness test
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis_ok() -> AsyncMock:
    """Mock redis client that responds to ping() successfully."""
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock


@pytest.fixture
def mock_redis_down() -> AsyncMock:
    """Mock redis client whose ping() raises a connection error."""
    mock = AsyncMock()
    mock.ping.side_effect = ConnectionError("Redis unavailable")
    return mock


@pytest.fixture
def mock_broker_ok() -> AsyncMock:
    """Mock FastStream RabbitBroker that reports as connected."""
    mock = AsyncMock()
    mock.connection = AsyncMock()
    mock.connection.is_closed = False
    return mock


@pytest.fixture
def mock_broker_down() -> AsyncMock:
    """Mock FastStream RabbitBroker that reports as disconnected."""
    mock = AsyncMock()
    mock.connection = None
    return mock
