"""Wave 0 stub-тесты WebSocket-аутентификации (RT-01a/b/c, D-04).

Реальная логика реализуется в плане 05-02 (router.py).
"""

from __future__ import annotations

import pytest

# Флаг доступности модулей realtime — проверяем при импорте
try:
    from app.realtime.router import router as _realtime_router  # noqa: F401

    _REALTIME_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _REALTIME_AVAILABLE = False


@pytest.mark.asyncio
async def test_invalid_token_closes_4008() -> None:
    """RT-01a: невалидный токен → закрытие соединения с кодом 4008."""
    pytest.skip("реализуется в плане 05-02")


@pytest.mark.asyncio
async def test_valid_token_accepts() -> None:
    """RT-01b: валидный токен → соединение принято."""
    pytest.skip("реализуется в плане 05-02")


@pytest.mark.asyncio
async def test_revoked_token() -> None:
    """RT-01c: отозванный токен (jti в blacklist) → закрытие 4008."""
    pytest.skip("реализуется в плане 05-02")


@pytest.mark.asyncio
async def test_inactive_user() -> None:
    """D-04: неактивный пользователь (is_active=False) → закрытие 4008."""
    pytest.skip("реализуется в плане 05-02")
