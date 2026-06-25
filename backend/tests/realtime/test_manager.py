"""Wave 0 stub-тест ConnectionManager (RT-03c).

Тест RT-03c будет наполнен в Task 3 этого плана (manager.py).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_fanout_skips_dead_connection() -> None:
    """RT-03c: мёртвое соединение при fan-out удаляется; остальные получают payload."""
    pytest.skip("реализуется в задаче 3 этого плана")
