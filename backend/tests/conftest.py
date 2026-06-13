"""Фикстуры pytest: async-engine, HTTP-клиенты и моки Redis/брокера/сессии для тестов здоровья."""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Бэкенд anyio для pytest-asyncio."""
    return "asyncio"


@pytest.fixture
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Создаёт временный async-engine на тестовый DATABASE_URL с NullPool."""
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


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP-клиент к приложению FastAPI с реальными подключениями."""
    try:
        from app.main import app  # noqa: PLC0415
    except ImportError:
        pytest.skip("app.main not yet implemented")
        return

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.fixture
def mock_redis_ok() -> AsyncMock:
    """Мок Redis, успешно отвечающий на ping()."""
    mock = AsyncMock()
    mock.ping.return_value = True
    return mock


@pytest.fixture
def mock_redis_down() -> AsyncMock:
    """Мок Redis, чей ping() бросает ошибку соединения."""
    mock = AsyncMock()
    mock.ping.side_effect = ConnectionError("Redis unavailable")
    return mock


@pytest.fixture
def mock_broker_ok() -> MagicMock:
    """Мок RabbitBroker в состоянии «подключён»."""
    mock = MagicMock()
    mock.connection = MagicMock()
    mock.connection.is_closed = False
    return mock


@pytest.fixture
def mock_broker_down() -> MagicMock:
    """Мок RabbitBroker в состоянии «не подключён»."""
    mock = MagicMock()
    mock.connection = None
    return mock


@pytest.fixture
def mock_session_ok() -> AsyncMock:
    """Мок AsyncSession, чей execute() успешен."""
    mock = AsyncMock(spec=AsyncSession)
    mock.execute.return_value = AsyncMock()
    return mock


@pytest.fixture
async def client_all_ok(
    mock_redis_ok: AsyncMock,
    mock_broker_ok: MagicMock,
    mock_session_ok: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient со всеми тремя зависимостями, замоканными как здоровые."""
    try:
        from app.db.session import get_async_session  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
    except ImportError:
        pytest.skip("app.main not yet implemented")
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

    app.dependency_overrides.clear()


@pytest.fixture
async def client_dep_down(
    mock_redis_down: AsyncMock,
    mock_broker_down: MagicMock,
) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient с Redis и RabbitMQ, замоканными как недоступные."""
    try:
        from app.db.session import get_async_session  # noqa: PLC0415
        from app.main import app  # noqa: PLC0415
    except ImportError:
        pytest.skip("app.main not yet implemented")
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

    app.dependency_overrides.clear()
