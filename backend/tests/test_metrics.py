"""
Metrics endpoint tests — NFR-01 criterion #2.

Tests:
  test_metrics_endpoint — GET /metrics returns prometheus metrics including
                          http_requests_total; body must NOT contain secrets.

This is a Wave 0 stub: collected now, skipped until app/main.py + instrumentation
are implemented in Wave 2/3.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint(client: AsyncClient) -> None:
    """GET /metrics must expose HTTP request counter and contain no secrets.

    NFR-01 criterion #2.

    Secure behaviour:
      - Response body must NOT contain 'password' (leaked config value).
      - Response body must NOT contain 'amqp://' (leaked DSN with credentials).
      - Response body MUST contain the prometheus metric for HTTP requests
        (http_requests_total or http_request_duration_seconds — instrumentator
        exposes at least one of these).
    """
    response = await client.get("/metrics")
    assert response.status_code == 200

    body = response.text

    # Secure behaviour: no secrets in /metrics output
    assert "password" not in body.lower(), (
        "/metrics response contains the word 'password' — possible secret leak"
    )
    assert "amqp://" not in body, (
        "/metrics response contains an AMQP DSN — possible credential leak"
    )

    # Content check: prometheus-fastapi-instrumentator registers at least one
    # of these metric families when requests have been made.
    http_metric_present = (
        "http_requests_total" in body
        or "http_request_duration_seconds" in body
        or "http_request_size_bytes" in body
    )
    assert http_metric_present, (
        "Expected at least one prometheus HTTP metric in /metrics output.\n"
        f"Body snippet: {body[:500]!r}"
    )
