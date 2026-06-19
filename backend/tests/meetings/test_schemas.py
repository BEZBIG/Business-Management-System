"""Юнит-тесты Pydantic-схем встреч (Wave 0 — заглушки).

Тела заполняются в планах 04-02 и 04-03.
"""

from __future__ import annotations

import pytest


def test_time_validation() -> None:
    """D-13: start >= end / прошедшее время / длительность вне границ → 422."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")


def test_max_participants() -> None:
    """D-14: более ~50 участников → 422."""
    pytest.skip("Wave 0 stub — filled in plan 04-02/04-03")
