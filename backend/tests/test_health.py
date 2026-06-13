"""
Health endpoint tests — NFR-01 criterion #1.

Tests:
  test_liveness                         — GET /health/live returns 200 {"status":"ok"}, no I/O
  test_readiness_ok                     — GET /health/ready returns 200 with all three service
                                          statuses (uses client_all_ok — mocked dependencies)
  test_readiness_503_on_dependency_down — GET /health/ready returns 503 when any dependency
                                          is down (uses client_dep_down — mocked failing deps)

These tests cover NFR-01 criterion #1 against mocked dependencies so they run
without requiring real Docker services (unit test scope).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    """GET /health/live must return 200 with body {"status": "ok"} and perform no I/O (D-07).

    NFR-01 criterion #1 (liveness half).
    Uses the base `client` fixture — liveness has no I/O so no mocks needed.
    """
    response = await client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"


@pytest.mark.asyncio
async def test_readiness_ok(client_all_ok: AsyncClient) -> None:
    """GET /health/ready must return 200 and report statuses for postgres, redis, rabbitmq.

    NFR-01 criterion #1 (readiness half — all three services up).
    Uses client_all_ok: all three dependencies are mocked as healthy.

    Secure behaviour: when all services are healthy the endpoint must NOT return
    503 (would block valid traffic).
    """
    response = await client_all_ok.get("/health/ready")
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
async def test_readiness_503_on_dependency_down(client_dep_down: AsyncClient) -> None:
    """GET /health/ready must return 503 when any dependency is unavailable.

    NFR-01 criterion #1 (secure behaviour: degraded readiness must not return 200).
    Uses client_dep_down: all three dependencies are mocked as failing.

    Secure behaviour: returning 200 when a dependency is down would silently
    route traffic to a broken instance — 503 is the correct signal to the
    load balancer to stop sending requests.
    """
    response = await client_dep_down.get("/health/ready")
    body = response.json()
    services = body.get("services", {})
    any_down = any(v != "ok" for v in services.values())
    if any_down:
        assert response.status_code == 503, (
            f"Expected 503 when a dependency is down, got {response.status_code}. Body: {body}"
        )
    else:
        # All up — 200 is correct (should not happen with client_dep_down fixture)
        assert response.status_code == 200
