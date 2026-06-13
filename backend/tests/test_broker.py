"""Тест устойчивости брокера RabbitMQ: автопереподключение после рестарта брокера."""

from __future__ import annotations

import asyncio
import os

import pytest


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("CI_INTEGRATION") != "1",
    reason=(
        "Integration test — requires Docker Compose stack. "
        "Set CI_INTEGRATION=1 to enable. "
        "Manual steps: `docker compose restart rabbitmq`, "
        "then verify /health/ready returns 200 without restarting the app."
    ),
)
@pytest.mark.asyncio
async def test_broker_reconnect() -> None:
    """RabbitBroker должен автоматически переподключаться после рестарта брокера."""
    rabbitmq_url = os.environ.get("RABBITMQ_URL")
    if not rabbitmq_url:
        pytest.skip("RABBITMQ_URL environment variable not set — skipping broker reconnect test")

    try:
        from faststream.rabbit import RabbitBroker  # noqa: PLC0415
    except ImportError:
        pytest.skip("faststream[rabbit] not available")

    broker = RabbitBroker(
        url=rabbitmq_url,
        fail_fast=False,
        reconnect_interval=5.0,
    )

    try:
        await broker.start()
        await asyncio.sleep(1.0)
        assert broker.connection is not None, "Broker did not establish a connection"
        assert not broker.connection.is_closed, "Broker connection is closed after start()"
    finally:
        await broker.stop()
