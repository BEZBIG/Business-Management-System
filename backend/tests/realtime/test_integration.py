"""Wave 0 интеграционные тесты real-time доставки событий (RT-02, RT-03a).

Требуют Docker Compose stack. Запускаются при CI_INTEGRATION=1.
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI_INTEGRATION") != "1",
    reason=(
        "Integration test — requires Docker Compose stack. "
        "Set CI_INTEGRATION=1 to enable."
    ),
)
@pytest.mark.asyncio
async def test_jitsi_link_delivery() -> None:
    """RT-02: Jitsi-ссылка доставляется участникам встречи через WebSocket."""
    pytest.skip("реализуется в планах 05-02 и 05-03")


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI_INTEGRATION") != "1",
    reason=(
        "Integration test — requires Docker Compose stack. "
        "Set CI_INTEGRATION=1 to enable."
    ),
)
@pytest.mark.asyncio
async def test_meeting_cancelled_delivery() -> None:
    """RT-03a: событие meeting_cancelled доставляется участникам через WebSocket."""
    pytest.skip("реализуется в планах 05-02 и 05-03")
