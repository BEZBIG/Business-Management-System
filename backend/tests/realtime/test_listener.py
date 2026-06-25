"""Wave 0 stub-тест Redis pub/sub listener (RT-01d).

Реальная логика реализуется в плане 05-03 (listener.py).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_listener_graceful_cancel() -> None:
    """RT-01d: отмена listener-таска (CancelledError) не вызывает исключений."""
    pytest.skip("реализуется в плане 05-03")
