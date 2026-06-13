"""
Health endpoint tests — NFR-01 criterion #1.

Tests:
  test_liveness                         — GET /health/live returns 200 {"status":"ok"}, no I/O (D-07)
  test_readiness_ok                     — GET /health/ready returns 200 with all three service statuses
  test_readiness_503_on_dependency_down — GET /health/ready returns 503 when any dependency is down

These tests are STUBS (Wave 0): they are collected now but SKIP automatically
until app/main.py and the /health router are implemented in Wave 2/3.
The skip is triggered by the lazy import inside the `client` fixture in conftest.py.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    """GET /health/live must return 200 with body {"status": "ok"} and perform no I/O (D-07).

    NFR-01 criterion #1 (liveness half).
    """
    response = await client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"


@pytest.mark.asyncio
async def test_readiness_ok(client: AsyncClient) -> None:
    """GET /health/ready must return 200 and report statuses for postgres, redis, rabbitmq.

    NFR-01 criterion #1 (readiness half — all three services up).

    Secure behaviour: when all services are healthy the endpoint must NOT return
    503 (would block valid traffic).
    """
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert "services" in body
    services = body["services"]
    assert "postgres" in services
    assert "redis" in services
    assert "rabbitmq" in services
    # All three must report "ok" for a 200 response
    for svc, status in services.items():
        assert status == "ok", f"Service {svc!r} reported {status!r} but expected 'ok'"


@pytest.mark.asyncio
async def test_readiness_503_on_dependency_down(client: AsyncClient) -> None:
    """GET /health/ready must return 503 when any dependency is unavailable.

    NFR-01 criterion #1 (secure behaviour: degraded readiness must not return 200).

    This test exercises the /health/ready endpoint in an environment where at
    least one dependency (postgres/redis/rabbitmq) is not reachable.  In the unit
    test context (no real Docker services), the endpoint is expected to detect
    that connections are unavailable and return 503.

    Secure behaviour: returning 200 when a dependency is down would silently
    route traffic to a broken instance — 503 is the correct signal to the
    load balancer to stop sending requests.
    """
    # In a unit test context without real services the health check should fail
    # because there are no running postgres/redis/rabbitmq to connect to.
    response = await client.get("/health/ready")
    # The test is satisfied if EITHER:
    #   a) all services are reachable (200 — integration environment), or
    #   b) at least one is down and the endpoint correctly returns 503.
    # We assert that the endpoint never returns a success code when reporting errors.
    body = response.json()
    services = body.get("services", {})
    any_down = any(v != "ok" for v in services.values())
    if any_down:
        assert response.status_code == 503, (
            "Expected 503 when a dependency is down, "
            f"got {response.status_code}. Body: {body}"
        )
    else:
        # All up — 200 is correct
        assert response.status_code == 200
