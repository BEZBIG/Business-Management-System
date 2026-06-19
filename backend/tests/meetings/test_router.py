"""Интеграционные тесты HTTP-роутера встреч и эндпоинта /calendar (Wave 0 — заглушки).

Тела заполняются в планах 04-02 и 04-03.
Интеграционные тесты требуют запущенной Docker-инфраструктуры.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
async def test_create_meeting() -> None:
    """MEET-01: POST /meetings создаёт встречу; jitsi_url доступна только участнику."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


@pytest.mark.integration
async def test_calendar_combined() -> None:
    """CAL-01: GET /calendar объединяет задачи и встречи с type-дискриминатором."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")
