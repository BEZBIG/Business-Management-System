"""Wave 0 stub-тест Prometheus gauge (RT-03b).

Реальная логика реализуется в плане 05-02 (router.py + try/finally).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_gauge_no_drift_on_disconnect() -> None:
    """RT-03b: gauge корректно уменьшается при отключении (нет дрейфа счётчика)."""
    pytest.skip("реализуется в плане 05-02")
