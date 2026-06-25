"""Тесты ConnectionManager (RT-03c): fan-out переживает мёртвые соединения."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

try:
    from app.realtime.manager import ConnectionManager  # noqa: PLC0415

    _MANAGER_AVAILABLE = True
except (ModuleNotFoundError, ImportError):
    _MANAGER_AVAILABLE = False


@pytest.mark.asyncio
async def test_fanout_skips_dead_connection() -> None:
    """RT-03c: мёртвое соединение при fan-out удаляется; живое получает payload."""
    if not _MANAGER_AVAILABLE:
        pytest.skip("app.realtime.manager not yet implemented")

    mgr = ConnectionManager()
    uid = "user-test-123"
    payload = {"type": "digest", "v": 1, "data": {}}

    # ws1 — мёртвое соединение: send_json бросает Exception
    ws1 = AsyncMock()
    ws1.send_json.side_effect = RuntimeError("broken pipe")

    # ws2 — живое соединение: send_json проходит успешно
    ws2 = AsyncMock()
    ws2.send_json.return_value = None

    mgr.add(uid, ws1)
    mgr.add(uid, ws2)

    # До fan-out оба соединения в реестре
    assert len(mgr.get(uid)) == 2

    await mgr.send_to_user(uid, payload)

    # ws2 получил payload
    ws2.send_json.assert_called_once_with(payload)

    # ws1 удалён из реестра после Exception
    remaining = mgr.get(uid)
    assert ws1 not in remaining, "мёртвое соединение должно быть удалено"
    assert ws2 in remaining, "живое соединение должно остаться"


@pytest.mark.asyncio
async def test_add_multi_device() -> None:
    """D-06: несколько соединений одного пользователя хранятся как set."""
    if not _MANAGER_AVAILABLE:
        pytest.skip("app.realtime.manager not yet implemented")

    mgr = ConnectionManager()
    uid = "multi-device-user"

    ws1 = AsyncMock()
    ws2 = AsyncMock()

    mgr.add(uid, ws1)
    mgr.add(uid, ws2)

    assert mgr.get(uid) == {ws1, ws2}


@pytest.mark.asyncio
async def test_remove_last_cleans_key() -> None:
    """Удаление последнего соединения убирает ключ user_id из dict."""
    if not _MANAGER_AVAILABLE:
        pytest.skip("app.realtime.manager not yet implemented")

    mgr = ConnectionManager()
    uid = "solo-user"
    ws = AsyncMock()

    mgr.add(uid, ws)
    assert uid in mgr._connections  # noqa: SLF001

    mgr.remove(uid, ws)
    assert uid not in mgr._connections  # noqa: SLF001


@pytest.mark.asyncio
async def test_get_returns_empty_for_unknown_user() -> None:
    """get() возвращает пустое множество для неизвестного user_id."""
    if not _MANAGER_AVAILABLE:
        pytest.skip("app.realtime.manager not yet implemented")

    mgr = ConnectionManager()
    assert mgr.get("ghost-user") == set()
