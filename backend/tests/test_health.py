# =============================================================================
# CBSHOME Backend -- Health & Readiness Endpoint Tests
# =============================================================================

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_all_ok(client: AsyncClient) -> None:
    """GET /health returns 200 with all components ok."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["db"] == "ok"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_db_down(client: AsyncClient) -> None:
    """GET /health returns 200 even when DB is down (degraded status)."""
    with patch(
        "app.main.get_engine",
        side_effect=Exception("DB unavailable"),
    ):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["db"] == "error"
    assert data["redis"] == "ok"


@pytest.mark.asyncio
async def test_health_redis_down(client: AsyncClient) -> None:
    """GET /health returns 200 even when Redis is down (degraded status)."""
    mock_redis = AsyncMock()
    mock_redis.ping.side_effect = Exception("Redis unavailable")
    with patch("app.main.get_redis", return_value=mock_redis):
        response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "degraded"
    assert data["db"] == "ok"
    assert data["redis"] == "error"


@pytest.mark.asyncio
async def test_ready_all_ok(client: AsyncClient) -> None:
    """GET /ready returns 200 when all components are healthy."""
    response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_ready_degraded_returns_503(client: AsyncClient) -> None:
    """GET /ready returns 503 when any component is down."""
    with patch(
        "app.main.get_engine",
        side_effect=Exception("DB unavailable"),
    ):
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@pytest.mark.asyncio
async def test_trace_id_in_response_headers(client: AsyncClient) -> None:
    """Every response includes X-Trace-ID header."""
    response = await client.get("/health")
    assert "x-trace-id" in response.headers


@pytest.mark.asyncio
async def test_custom_trace_id_echoed(client: AsyncClient) -> None:
    """X-Trace-ID from request is echoed back in response."""
    custom_id = "my-custom-trace-42"
    response = await client.get("/health", headers={"X-Trace-ID": custom_id})
    assert response.headers.get("x-trace-id") == custom_id
