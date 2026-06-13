"""Тесты эндпоинта метрик: /metrics отдаёт HTTP-счётчик Prometheus и не содержит секретов."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient) -> None:
    """GET /metrics должен отдавать HTTP-счётчик запросов и не содержать секретов."""
    response = await client.get("/metrics")
    assert response.status_code == 200

    body = response.text

    assert "password" not in body.lower(), (
        "/metrics response contains the word 'password' — possible secret leak"
    )
    assert "amqp://" not in body, (
        "/metrics response contains an AMQP DSN — possible credential leak"
    )

    http_metric_present = (
        "http_requests_total" in body
        or "http_request_duration_seconds" in body
        or "http_request_size_bytes" in body
    )
    assert http_metric_present, (
        "Expected at least one prometheus HTTP metric in /metrics output.\n"
        f"Body snippet: {body[:500]!r}"
    )
