"""Юнит-тесты сервисного слоя встреч (Wave 0 — заглушки).

Тела заполняются в планах 04-02 и 04-03.
Каждая заглушка вызывает pytest.skip, чтобы не давать ложно-зелёных результатов.
"""

from __future__ import annotations

import pytest


def test_invalid_participant() -> None:
    """MEET-01: участник не из команды → 422."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_conflict_409() -> None:
    """MEET-02: конфликтующая встреча → 409 с деталями."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_back_to_back_ok() -> None:
    """MEET-02: back-to-back встречи → 201 (строгий оператор <, не конфликт)."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_lock_order() -> None:
    """MEET-02: advisory lock берётся в детерминированном порядке (анти-дедлок)."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_cancel_owner() -> None:
    """MEET-03: owner отменяет встречу → status=cancelled."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_cancel_participant_403() -> None:
    """MEET-03: участник (не owner) пытается отменить → 403."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_cancelled_not_in_conflict() -> None:
    """MEET-03: отменённая встреча исключается из проверки конфликтов."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_jitsi_token_format() -> None:
    """MEET-04: jitsi_room_token генерируется через secrets.token_urlsafe(32)."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_jitsi_url_participant_only() -> None:
    """MEET-04: jitsi_url не раскрывается не-участнику встречи."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_calendar_month_range() -> None:
    """CAL-02: view=month → диапазон полного месяца."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_calendar_week_range() -> None:
    """CAL-03: view=week → диапазон недели."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_calendar_day_range() -> None:
    """CAL-04: view=day → диапазон одного дня."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")
