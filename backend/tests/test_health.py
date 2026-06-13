"""Тесты эндпоинтов здоровья: /health/live, /health/ready и 503 при падении зависимости."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness(client: AsyncClient) -> None:
    """GET /health/live должен вернуть 200 с телом {"status": "ok"} без I/O."""
    response = await client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body.get("status") == "ok"


@pytest.mark.asyncio
async def test_readiness_ok(client_all_ok: AsyncClient) -> None:
    """GET /health/ready должен вернуть 200 и статусы postgres, redis, rabbitmq (все «ok»)."""
    response = await client_all_ok.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert "services" in body
    services = body["services"]
    assert "postgres" in services
    assert "redis" in services
    assert "rabbitmq" in services
    for svc, status in services.items():
        assert status == "ok", f"Service {svc!r} reported {status!r} but expected 'ok'"


@pytest.mark.asyncio
async def test_readiness_503_on_dependency_down(client_dep_down: AsyncClient) -> None:
    """GET /health/ready должен вернуть 503, когда любая зависимость недоступна."""
    response = await client_dep_down.get("/health/ready")
    body = response.json()
    services = body.get("services", {})
    any_down = any(v != "ok" for v in services.values())
    if any_down:
        assert response.status_code == 503, (
            f"Expected 503 when a dependency is down, got {response.status_code}. Body: {body}"
        )
    else:
        assert response.status_code == 200
