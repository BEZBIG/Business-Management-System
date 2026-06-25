"""Тесты publish_event helper и интеграционные тесты real-time доставки.

Unit-тесты publish_event (не требуют Docker stack) проверяют,
что redis.publish вызывается с корректным каналом и JSON-payload.

Integration-тесты (RT-02, RT-03a) требуют Docker Compose stack; запускаются при CI_INTEGRATION=1.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.realtime.publisher import publish_event
from app.realtime.schemas import JitsiLinkData, JitsiLinkEvent


# ---------------------------------------------------------------------------
# Unit-тесты publish_event (без Docker-стека)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_event_calls_redis_publish() -> None:
    """publish_event вызывает redis.publish с каналом notifications:<uid> и валидным JSON."""
    mock_redis = AsyncMock()
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    now = datetime.now(UTC)

    event = JitsiLinkEvent(
        type="jitsi_link",
        ts=now,
        data=JitsiLinkData(
            meeting_id=meeting_id,
            meeting_title="Тест встречи",
            jitsi_url="https://meet.jit.si/fake_token",
            start_time=now,
        ),
    )

    await publish_event(mock_redis, user_id, event)

    # Проверяем, что redis.publish был вызван ровно один раз
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    channel, payload = call_args[0]

    # Канал должен быть notifications:<user_id>
    assert channel == f"notifications:{user_id}"

    # payload — валидный JSON с нужным типом события
    decoded = json.loads(payload)
    assert decoded["type"] == "jitsi_link"
    assert str(meeting_id) in json.dumps(decoded)


@pytest.mark.asyncio
async def test_publish_event_channel_format() -> None:
    """publish_event формирует канал точно как notifications:{user_id}."""
    mock_redis = AsyncMock()
    user_id = "test-user-42"

    event = JitsiLinkEvent(
        type="jitsi_link",
        ts=datetime.now(UTC),
        data=JitsiLinkData(
            meeting_id=uuid.uuid4(),
            meeting_title="Meeting",
            jitsi_url="https://meet.jit.si/abc",
            start_time=datetime.now(UTC),
        ),
    )

    await publish_event(mock_redis, user_id, event)

    channel = mock_redis.publish.call_args[0][0]
    assert channel == "notifications:test-user-42"


@pytest.mark.asyncio
async def test_publish_event_payload_is_model_dump_json() -> None:
    """publish_event передаёт payload = event.model_dump_json() (ts ISO-8601, UUID как str)."""
    mock_redis = AsyncMock()
    user_id = str(uuid.uuid4())
    meeting_id = uuid.uuid4()
    now = datetime.now(UTC)

    event = JitsiLinkEvent(
        type="jitsi_link",
        ts=now,
        data=JitsiLinkData(
            meeting_id=meeting_id,
            meeting_title="Test",
            jitsi_url="https://meet.jit.si/tok",
            start_time=now,
        ),
    )

    expected_payload = event.model_dump_json()
    await publish_event(mock_redis, user_id, event)

    actual_payload = mock_redis.publish.call_args[0][1]
    assert actual_payload == expected_payload

    # UUID должен быть строкой в JSON
    decoded = json.loads(actual_payload)
    assert isinstance(decoded["data"]["meeting_id"], str)


# ---------------------------------------------------------------------------
# Integration-тесты (требуют Docker Compose stack + uvicorn --workers 2)
# ---------------------------------------------------------------------------


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
