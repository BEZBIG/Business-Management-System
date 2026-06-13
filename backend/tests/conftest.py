"""
pytest conftest for the TeamFlow backend test suite.

Fixtures provided:
  - anyio_backend      : force asyncio backend for pytest-asyncio
  - async_engine       : SQLAlchemy AsyncEngine with NullPool (safe for parallel fixtures)
  - client             : httpx AsyncClient backed by the FastAPI ASGI app (real services)
  - client_all_ok      : AsyncClient with all three dependencies mocked as healthy (unit tests)
  - client_dep_down    : AsyncClient with at least one dependency mocked as down (unit tests)
  - mock_redis_ok      : Redis mock that responds to ping() successfully
  - mock_redis_down    : Redis mock that raises ConnectionError on ping()
  - mock_broker_ok     : RabbitBroker mock that reports as connected (connection.is_closed=False)
  - mock_broker_down   : RabbitBroker mock that reports as disconnected (connection=None)

Design notes:
  - NullPool is used to avoid connection-pool state leaking between test functions
    (see RESEARCH.md Pitfall / Pattern 12).  Each test function gets a fresh
    connection; this is slightly slower but correct.
  - The `app` import is deferred inside the fixture so that `pytest --collect-only`
    succeeds even before Wave 2/3 create app/main.py.  Collection will succeed;
    the fixture itself will fail only when the test *runs*.
  - client_all_ok patches app.health.router.redis_client and app.health.router.broker
    at the module level so that /health/ready uses mock objects instead of real
    connections. get_async_session is overridden via FastAPI dependency_overrides.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
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
        os.environ.get(
            "DATABASE_URL", "postgresql+asyncpg://teamflow:teamflow@localhost/teamflow_test"
        ),
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

    NOTE: This fixture uses real external connections. Tests that need isolated
    unit-test behaviour (no real PG/Redis/Rabbit) should use `client_all_ok`
    or `client_dep_down` instead.
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
# Dependency mocks for /health/ready readiness tests
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
def mock_broker_ok() -> MagicMock:
    """Mock FastStream RabbitBroker that reports as connected."""
    mock = MagicMock()
    mock.connection = MagicMock()
    mock.connection.is_closed = False
    return mock


@pytest.fixture
def mock_broker_down() -> MagicMock:
    """Mock FastStream RabbitBroker that reports as disconnected."""
    mock = MagicMock()
    mock.connection = None
    return mock


@pytest.fixture
def mock_session_ok() -> AsyncMock:
    """Mock AsyncSession whose execute() succeeds (simulates SELECT 1 success)."""
    mock = AsyncMock(spec=AsyncSession)
    mock.execute.return_value = AsyncMock()
    return mock


# ---------------------------------------------------------------------------
# Patched clients for unit tests (no real services needed)
# ---------------------------------------------------------------------------


@pytest.fixture
async def client_all_ok(
    mock_redis_ok: AsyncMock,
    mock_broker_ok: MagicMock,
    mock_session_ok: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with all three dependencies mocked as healthy.

    Use this fixture in tests that verify /health/ready returns 200 without
    requiring real PostgreSQL / Redis / RabbitMQ connections.

    Patching strategy:
      - redis_client and broker are module-level singletons in app.health.router;
        they are patched with unittest.mock.patch for the duration of the test.
      - get_async_session is overridden via FastAPI dependency_overrides so the
        DI system injects the mock session instead of opening a real DB connection.
    """
    try:
        from app.db.session import get_async_session  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
    except ImportError:
        pytest.skip("app.main not yet implemented (Wave 2+)")
        return

    async def _mock_session() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session_ok  # type: ignore[misc]

    app.dependency_overrides[get_async_session] = _mock_session

    with (
        patch("app.health.router.redis_client", mock_redis_ok),
        patch("app.health.router.broker", mock_broker_ok),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    # Restore overrides after test
    app.dependency_overrides.clear()


@pytest.fixture
async def client_dep_down(
    mock_redis_down: AsyncMock,
    mock_broker_down: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with Redis and RabbitMQ mocked as unavailable.

    Use this fixture in tests that verify /health/ready returns 503 when
    at least one dependency is down.

    Postgres will also fail (no real DB) — all three report 'error'.
    """
    try:
        from app.db.session import get_async_session  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
    except ImportError:
        pytest.skip("app.main not yet implemented (Wave 2+)")
        return

    failing_session = AsyncMock(spec=AsyncSession)
    failing_session.execute.side_effect = ConnectionError("Database unavailable")

    async def _failing_session() -> AsyncGenerator[AsyncSession, None]:
        yield failing_session  # type: ignore[misc]

    app.dependency_overrides[get_async_session] = _failing_session

    with (
        patch("app.health.router.redis_client", mock_redis_down),
        patch("app.health.router.broker", mock_broker_down),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac

    # Restore overrides after test
    app.dependency_overrides.clear()
